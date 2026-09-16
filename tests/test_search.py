import time
import pytest
from mother.app import create_app
from mother.store import Store
from mother.search import SearchService, EmbeddingError, DIMENSIONS, chunk_text, validate_vectors, LocalEmbedder


class FakeEmbedder:
    def __init__(self):
        self.calls = []
        self.fail = False

    def embed(self, texts, query=False):
        self.calls.append((list(texts), query))
        if self.fail:
            raise EmbeddingError('Ollama is unavailable for this test.')
        vectors = []
        for text in texts:
            v = [0.0] * DIMENSIONS
            words = text.lower()
            position = 0 if any(w in words for w in ('automobile', 'car', 'vehicle')) else 1 if any(w in words for w in ('garden', 'flower')) else 2
            v[position] = 1.0
            vectors.append(v)
        return vectors


@pytest.fixture
def search_setup(tmp_path):
    app = create_app(tmp_path / 'data')
    store = app.extensions['store']
    embedder = FakeEmbedder()
    service = SearchService(store, embedder)
    return app, store, service, embedder


def test_semantic_synonyms_and_exact_text_remain_distinct(search_setup):
    app, store, service, embedder = search_setup
    car = store.create_conversation('Vehicle notes')['id']
    car_event = store.add(car, 'user', 'You', 'The car needs a new battery.')
    garden = store.create_conversation('Garden')['id']
    store.add(garden, 'reply', 'Assistant', 'Water the flowers in the garden.')
    store.add(garden, 'run', 'Mother', 'Private configuration snapshot')
    store.add(garden, 'system', 'Mother', 'Discussion complete.')
    service.process_pending()
    assert service.status()['indexed'] == 2
    assert service.search('automobile', mode='keyword')['results'] == []
    found = service.search('automobile')['results']
    assert found[0]['id'] == car_event['id'] and found[0]['match_type'] == 'meaning'
    assert 'car' in found[0]['snippet']
    assert service.search('battery')['results'][0]['match_type'] == 'text + meaning'
    assert service.fulltext('battery new')[0]['id'] == car_event['id']
    assert all(e['kind'] in ('user', 'reply') for e in service.search('Private configuration')['results'])
    before = len(embedder.calls)
    service.search('automobile')
    service.search('automobile')
    assert len(embedder.calls) == before  # repeated queries reuse local vectors


def test_index_is_durable_incremental_and_repeated_indexing_is_idempotent(search_setup):
    _, store, service, embedder = search_setup
    cid = store.create_conversation('Durable')['id']
    event = store.add(cid, 'reply', 'Assistant', 'car ' * 1500)
    service.process_pending()
    assert service.status()['chunks'] > 1
    original = service.status()['chunks']
    calls = len(embedder.calls)
    service.process_pending()
    assert len(embedder.calls) == calls
    reopened = Store(store.root)
    other = SearchService(reopened, embedder)
    assert other.status()['indexed'] == 1
    other.index_event(event)
    assert other.status()['chunks'] == original
    reopened.add(cid, 'user', 'You', 'flower garden')
    other.process_pending()
    assert other.status()['indexed'] == 2
    assert len(other.semantic('vehicle', cid=cid)) == 2  # chunks deduplicate to messages


def test_trash_is_filtered_before_nearest_neighbor_limit(search_setup):
    _, store, service, _ = search_setup
    trash = store.create_conversation('Discarded')['id']
    for _ in range(201):
        store.add(trash, 'user', 'You', 'car')
    kept = store.create_conversation('Keep')['id']
    event = store.add(kept, 'user', 'You', 'flower garden')
    service.process_pending()
    assert store.delete_conversation(trash)
    assert [r['id'] for r in service.semantic('automobile')] == [event['id']]
    assert service.fulltext('car') == []
    assert service.status()['indexed'] == 1
    assert store.restore_conversation(trash)
    assert service.semantic('automobile')[0]['conversation_id'] == trash
    assert service.status()['indexed'] == 202
    store.rename_conversation(trash, 'Restored name')
    assert service.semantic('automobile')[0]['title'] == 'Restored name'


def test_date_and_conversation_filters_apply_to_vectors(search_setup):
    _, store, service, _ = search_setup
    first = store.create_conversation('First')['id']
    second = store.create_conversation('Second')['id']
    early = store.add(first, 'user', 'You', 'car battery')
    late = store.add(second, 'user', 'You', 'flower')
    with store.connect() as db:
        db.execute('UPDATE events SET created_at=? WHERE id=?', ('2026-01-01T00:00:00Z', early['id']))
        db.execute('UPDATE events SET created_at=? WHERE id=?', ('2026-02-01T00:00:00Z', late['id']))
    service.process_pending()
    assert [r['id'] for r in service.semantic('automobile', start='2026-02-01')] == [late['id']]
    assert [r['id'] for r in service.semantic('automobile', end='2026-01-31', cid=first)] == [early['id']]
    assert service.semantic('automobile', start='2026-02-01', cid=first) == []
    assert service.search('car', start='2026-02-01', mode='keyword')['results'] == []


def test_failed_batches_are_atomic_and_text_search_survives(search_setup):
    _, store, service, embedder = search_setup
    cid = store.create_conversation('Failure')['id']
    store.add(cid, 'reply', 'Assistant', 'car battery')
    embedder.fail = True
    service.process_pending()
    status = service.status()
    assert status['indexed'] == status['chunks'] == 0 and status['failed'] == 1
    assert service.search('battery')['results'][0]['content'] == 'car battery'
    assert 'unavailable' in service.search('battery')['warning']
    calls = len(embedder.calls)
    service.process_pending()
    assert len(embedder.calls) == calls
    embedder.fail = False
    service.retry()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and service.status()['pending']:
        time.sleep(.02)
    service.stop()
    service.worker.join(1)
    assert service.status()['indexed'] == 1 and service.status()['failed'] == 0


def test_query_outage_falls_back_to_text_without_losing_matches(search_setup):
    _, store, service, embedder = search_setup
    cid = store.create_conversation('Outage')['id']
    store.add(cid, 'user', 'You', 'car battery')
    service.process_pending()
    embedder.fail = True
    result = service.search('battery')
    assert result['results'][0]['content'] == 'car battery'
    assert result['warning'] and result['results'][0]['match_type'] == 'text'


def test_long_text_chunking_preserves_tail_and_checks_overlap():
    text = 'Car. ' * 1200 + 'THE FINAL DETAIL'
    parts = chunk_text(text)
    assert len(parts) > 1 and parts[-1].endswith('THE FINAL DETAIL')
    assert all(len(part) <= 2000 for part in parts)
    assert chunk_text('  ') == []
    with pytest.raises(ValueError):
        chunk_text('text', size=10, overlap=10)


@pytest.mark.parametrize('vectors', [[], [[1.] * 3], [[0.] * DIMENSIONS], [[float('nan')] * DIMENSIONS]])
def test_invalid_embedding_batches_rejected(vectors):
    with pytest.raises(EmbeddingError):
        validate_vectors(vectors, 1)


def test_partial_provider_response_leaves_no_partial_index(search_setup):
    _, store, service, embedder = search_setup
    cid = store.create_conversation('Incomplete')['id']
    store.add(cid, 'reply', 'Assistant', 'car ' * 1500)
    embedder.embed = lambda texts, query=False: [[1.] * DIMENSIONS]
    service.process_pending()
    assert service.status()['chunks'] == service.status()['indexed'] == 0
    assert service.status()['failed'] == 1


def test_search_api_validation_and_offline_keyword_search(search_setup):
    app, store, _, _ = search_setup
    cid = store.create_conversation('API')['id']
    store.add(cid, 'user', 'You', 'Literal 100% word_with_underscore')
    client = app.test_client()
    result = client.get('/api/search/hybrid', query_string={'q': '100%', 'mode': 'keyword'})
    assert result.status_code == 200 and len(result.json['results']) == 1
    assert client.get('/api/search/status').json['pending'] == 1
    for args in ({'q':'x'*1001}, {'start':'not-a-date'}, {'start':'2026-02-01','end':'2026-01-01'}, {'mode':'unsupported'}):
        assert client.get('/api/search/hybrid', query_string=args).status_code == 400
    # User text is quoted as FTS terms, never executed as an FTS expression.
    assert client.get('/api/search/hybrid', query_string={'q':'" OR * NEAR(foo)'}).status_code == 200


def test_local_embedding_adapter_payload_and_validation(monkeypatch):
    calls = []
    class Response:
        ok = True
        status_code = 200
        def json(self):
            return {'embeddings': [[1.] * DIMENSIONS]}
    def post(url, **kwargs):
        calls.append((url,kwargs))
        return Response()
    monkeypatch.setattr('mother.search.requests.post', post)
    LocalEmbedder().embed(['automobile'], query=True)
    assert calls[0][0] == 'http://127.0.0.1:11434/api/embed'
    assert calls[0][1]['json']['input'] == ['search_query: automobile']
    assert calls[0][1]['json']['truncate'] is False
