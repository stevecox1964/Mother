import json
import threading
import time
import pytest
from mother.app import create_app
from mother.config import Config
from mother.store import Store
from mother import providers, workspace


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path / "data")
    app.config["TESTING"] = True
    cfg = app.extensions["mother_config"]
    settings = cfg.read()
    settings["models"] = [
        cfg.profile("chief", "Chief", "demo", "simulated", "Synthesize"),
        cfg.profile("peer", "Peer", "demo", "simulated", "Review"),
    ]
    cfg.save(settings)
    return app


def wait_run(store, rid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = store.run(rid)
        if run["status"] != "running":
            return run
        time.sleep(0.02)
    raise AssertionError("run did not finish")


@pytest.mark.parametrize("legacy_rounds", [1, 2, 3])
def test_default_chat_persists_exactly_one_reply(app, legacy_rounds):
    cfg = app.extensions["mother_config"]
    settings = cfg.read()
    settings["rounds"] = legacy_rounds
    cfg.save(settings)
    c = app.test_client()
    store = app.extensions["store"]
    cid = c.post("/api/conversations", json={"title": "Architecture"}).json["id"]
    r = c.post(
        f"/api/conversations/{cid}/messages",
        json={"content": "Plan the storage design"},
    )
    assert r.status_code == 202
    assert wait_run(store, r.json["id"])["status"] == "completed"
    events = c.get(f"/api/conversations/{cid}").json["events"]
    assert [e["kind"] for e in events] == ["user", "run", "reply"]
    assert events[-1]["author"] == "Chief"
    assert (
        c.get(f"/api/conversations/{cid}?after={events[-2]['seq']}").json["events"]
        == events[-1:]
    )
    assert (
        c.get(f"/api/conversations/{cid}?after={events[-1]['seq']}").json["events"]
        == []
    )
    files = list(store.root.glob("conversations/*/*/*/*.jsonl"))
    mirrored = [
        json.loads(line)
        for f in files
        for line in f.read_text(encoding="utf-8").splitlines()
    ]
    assert mirrored == events
    assert c.get("/api/search?q=storage").json[0]["conversation_id"] == cid
    assert len(c.get(f"/api/conversations/{cid}/export").data.splitlines()) == len(
        events
    )
    reopened = Store(store.root)
    assert reopened.events(cid) == events


def test_direct_chat_targets_only_one_model(app):
    c = app.test_client()
    s = app.extensions["store"]
    cid = c.post("/api/conversations", json={"title": "Direct"}).json["id"]
    r = c.post(
        f"/api/conversations/{cid}/messages",
        json={"content": "Hello", "targets": ["peer"]},
    )
    wait_run(s, r.json["id"])
    replies = [
        e for e in s.events(cid) if e["kind"] in ("reply", "synthesis", "contribution")
    ]
    assert len(replies) == 1 and replies[0]["author"] == "Peer"


def test_chat_context_and_followup_make_one_call_each(app, tmp_path, monkeypatch):
    cfg = app.extensions["mother_config"]
    s = app.extensions["store"]
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("SOURCE_EVIDENCE = 42")
    settings = cfg.read()
    settings.update(project_path=str(project), context_files=["app.py"])
    settings["models"][1]["context_mode"] = "files"
    cfg.save(settings)
    calls = []

    def complete(p, system, prompt, key, images, **kwargs):
        calls.append((p["id"], system, prompt))
        return {
            "text": "PEER_FINDING" if p["id"] == "peer" else "CHIEF_VIEW",
            "usage": {},
        }

    monkeypatch.setattr(providers, "complete", complete)
    c = app.test_client()
    cid = c.post("/api/conversations", json={"title": "Code"}).json["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "Review"})
    wait_run(s, r.json["id"])
    assert len(calls) == 1
    assert calls[0][0] == "chief" and "SOURCE_EVIDENCE" not in calls[0][2]
    assert "Answer the user's latest message once" in calls[0][1]
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "Now review the code", "targets": ["peer"]})
    assert wait_run(s, r.json["id"])["status"] == "completed"
    assert len(calls) == 2
    assert calls[1][0] == "peer" and "SOURCE_EVIDENCE" in calls[1][2]
    assert "CHIEF_VIEW" in calls[1][2] and "Now review the code" in calls[1][2]
    assert [e["kind"] for e in s.events(cid)] == ["user", "run", "reply"] * 2


def test_failure_is_visible_once_without_retry_or_summary(app, monkeypatch):
    calls = []
    def complete(p, *args, **kwargs):
        calls.append(p["id"])
        raise providers.ProviderError("Provider HTTP 429.")

    monkeypatch.setattr(providers, "complete", complete)
    c = app.test_client()
    s = app.extensions["store"]
    cid = c.post("/api/conversations", json={}).json["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "Hello"})
    assert wait_run(s, r.json["id"])["status"] == "completed_with_errors"
    assert calls == ["chief"]
    assert [e["kind"] for e in s.events(cid)] == ["user", "run", "error"]


def test_chat_rejects_multiple_targets_and_falls_back_to_enabled_model(app):
    c = app.test_client()
    store = app.extensions["store"]
    cid = c.post("/api/conversations", json={}).json["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "Hello", "targets": ["chief", "peer"]})
    assert r.status_code == 400 and store.events(cid) == []
    cfg = app.extensions["mother_config"]
    settings = cfg.read()
    settings["models"][0]["enabled"] = False
    cfg.save(settings)
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "Hello"})
    assert wait_run(store, r.json["id"])["status"] == "completed"
    assert store.events(cid)[-1]["author"] == "Peer"


def test_cancel_discards_inflight_and_prevents_followups(app, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def complete(*args, **kwargs):
        entered.set()
        release.wait(4)
        return {"text": "LATE_REPLY", "usage": {}}

    monkeypatch.setattr(providers, "complete", complete)
    c = app.test_client()
    s = app.extensions["store"]
    cid = c.post("/api/conversations", json={}).json["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "Discuss"})
    assert entered.wait(2)
    assert (
        c.post(
            f"/api/conversations/{cid}/messages", json={"content": "Duplicate"}
        ).status_code
        == 409
    )
    assert (
        c.post("/api/runs/" + r.json["id"] + "/cancel", json={}).json["status"]
        == "cancelled"
    )
    release.set()
    time.sleep(0.15)
    assert not any("LATE_REPLY" in e["content"] for e in s.events(cid))


def test_settings_credentials_restart_and_local_origin(app):
    c = app.test_client()
    cfg = app.extensions["mother_config"]
    assert (
        c.put(
            "/api/credentials",
            json={"name": "OPENAI_API_KEY", "value": "test-private-key"},
        ).status_code
        == 200
    )
    data = c.get("/api/settings").data.decode()
    assert "test-private-key" not in data
    assert cfg.key({"api_key_env": "OPENAI_API_KEY"}) == "test-private-key"
    assert Config(cfg.root).key({"api_key_env": "OPENAI_API_KEY"}) == "test-private-key"
    assert (
        c.put(
            "/api/credentials", json={"name": "OPENAI_API_KEY", "value": "a\nOTHER=bad"}
        ).status_code
        == 400
    )
    assert (
        c.post(
            "/api/conversations", json={}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert c.get("/api/settings", headers={"Host": "evil.example"}).status_code == 403
    settings = cfg.read()
    settings["models"][1]["id"] = "chief"
    assert c.put("/api/settings", json=settings).status_code == 400


def test_restart_marks_active_run_interrupted_and_repairs_mirror(app):
    s = app.extensions["store"]
    cid = s.create_conversation("Restart")["id"]
    r = s.start_run(cid)
    s.add(cid, "user", "You", "durable")
    file = next(s.root.glob("conversations/*/*/*/*.jsonl"))
    file.write_text("broken")
    reopened = Store(s.root)
    assert reopened.run(r["id"])["status"] == "interrupted"
    events = reopened.events(cid)
    assert events[-1]["kind"] == "system"
    assert [json.loads(x) for x in file.read_text().splitlines()] == events


def test_workspace_rejects_escape_credentials_and_over_budget(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print(42)")
    (project / ".env").write_text("PRIVATE=example")
    (project / ".pytest_cache").mkdir()
    (project / ".pytest_cache" / "README.md").write_text("cache")
    (tmp_path / "outside.py").write_text("outside")
    assert [f["path"] for f in workspace.list_files(str(project))["files"]] == [
        "main.py"
    ]
    cfg = dict(
        project_path=str(project), context_files=["main.py"], max_context_chars=1000
    )
    text, manifest = workspace.snapshot(cfg)
    assert "print(42)" in text and len(manifest[0]["sha256"]) == 64
    for file in ("../outside.py", ".env"):
        with pytest.raises(ValueError):
            workspace.snapshot({**cfg, "context_files": [file]})
    with pytest.raises(ValueError):
        workspace.snapshot({**cfg, "max_context_chars": 1})


@pytest.mark.parametrize(
    "provider,body,text",
    [
        (
            "openai",
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Answer"}],
                    }
                ]
            },
            "Answer",
        ),
        (
            "anthropic",
            {
                "content": [
                    {"type": "thinking", "thinking": "hidden"},
                    {"type": "text", "text": "Answer"},
                ]
            },
            "Answer",
        ),
        (
            "gemini",
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "hidden", "thought": True},
                                {"text": "Answer"},
                            ]
                        }
                    }
                ]
            },
            "Answer",
        ),
        ("ollama", {"message": {"content": "<think>hidden</think>Answer"}}, "Answer"),
        ("compatible", {"choices": [{"message": {"content": "Answer"}}]}, "Answer"),
    ],
)
def test_provider_wire_formats(provider, body, text, monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return body

    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr(providers.requests, "post", post)
    p = Config.profile("id", "Name", provider, "model-id", "soul")
    result = providers.complete(p, "SYSTEM", "PROMPT", "PRIVATE_KEY")
    assert result["text"] == text
    assert "PRIVATE_KEY" not in json.dumps(captured["json"])
    assert captured["allow_redirects"] is False
    if provider == "openai":
        assert captured["json"]["store"] is False
    if provider == "gemini":
        assert captured["headers"]["x-goog-api-key"] == "PRIVATE_KEY"


def test_image_validation_and_routing(app, monkeypatch):
    import base64

    cfg = app.extensions["mother_config"]
    settings = cfg.read()
    settings["models"][1]["vision"] = True
    cfg.save(settings)
    calls = []

    def complete(p, system, prompt, key, images, **kwargs):
        calls.append((p["id"], images))
        return {"text": "Image reply", "usage": {}}

    monkeypatch.setattr(providers, "complete", complete)
    c = app.test_client()
    cid = c.post("/api/conversations", json={}).json["id"]
    data = {
        "content": "Describe",
        "images": [
            {
                "name": "pixel.png",
                "base64": base64.b64encode(b"\x89PNG\r\n\x1a\nimage").decode(),
            }
        ],
    }
    assert c.post(f"/api/conversations/{cid}/messages", json=data).status_code == 400
    assert calls == []
    data["targets"] = ["peer"]
    r = c.post(f"/api/conversations/{cid}/messages", json=data)
    assert r.status_code == 202
    wait_run(app.extensions["store"], r.json["id"])
    assert len(calls) == 1 and calls[0][0] == "peer" and len(calls[0][1]) == 1
    data["images"][0]["base64"] = "invalid"
    assert c.post(f"/api/conversations/{cid}/messages", json=data).status_code == 400

def test_conversation_rename_trash_restore_and_persistence(app):
    c = app.test_client()
    store = app.extensions['store']
    cid = c.post('/api/conversations', json={'title': 'Original'}).json['id']
    event = store.add(cid, 'user', 'You', 'Searchable conversation content')
    assert c.put(f'/api/conversations/{cid}', json={'title': '  Renamed  '}).json['title'] == 'Renamed'
    assert c.get('/api/conversations').json[0]['title'] == 'Renamed'
    assert c.get('/api/search?q=Searchable').json[0]['title'] == 'Renamed'
    for bad in (' ', 'x' * 161, None, 42):
        assert c.put(f'/api/conversations/{cid}', json={'title': bad}).status_code == 400
    assert c.delete(f'/api/conversations/{cid}', json={}).status_code == 200
    assert c.get('/api/conversations').json == []
    assert c.get('/api/search?q=Searchable').json == []
    assert c.get(f'/api/conversations/{cid}').status_code == 404
    assert c.get(f'/api/conversations/{cid}/export').status_code == 404
    assert c.post(f'/api/conversations/{cid}/messages', json={'content': 'Hello'}).status_code == 404
    assert c.get('/api/trash').json[0]['title'] == 'Renamed'
    reopened = Store(store.root)
    assert not reopened.exists(cid) and reopened.deleted_conversations()[0]['id'] == cid
    assert c.post(f'/api/conversations/{cid}/restore', json={}).status_code == 200
    assert c.get('/api/trash').json == []
    assert c.get(f'/api/conversations/{cid}').json['events'] == [event]
    assert b'Searchable conversation content' in c.get(f'/api/conversations/{cid}/export').data
    assert c.post(f'/api/conversations/{cid}/restore', json={}).status_code == 404


def test_conversation_cannot_be_deleted_during_reply(app):
    c = app.test_client()
    store = app.extensions['store']
    cid = c.post('/api/conversations', json={}).json['id']
    run = store.start_run(cid)
    r = c.delete(f'/api/conversations/{cid}', json={})
    assert r.status_code == 400 and 'Stop' in r.json['error']
    assert store.exists(cid)
    store.finish(run['id'], 'cancelled')
    assert c.delete(f'/api/conversations/{cid}', json={}).status_code == 200
    with pytest.raises(ValueError):
        store.start_run(cid)


def test_legacy_conversation_schema_migrates(tmp_path):
    import sqlite3
    root = tmp_path / 'legacy'
    root.mkdir()
    with sqlite3.connect(root / 'mother.db') as db:
        db.execute('CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL)')
        db.execute("INSERT INTO conversations VALUES ('legacy', 'Existing chat', '2026-09-05T00:00:00Z')")
    store = Store(root)
    assert store.conversations()[0]['title'] == 'Existing chat'
    assert store.delete_conversation('legacy')
    assert Store(root).restore_conversation('legacy')
    assert store.exists('legacy')
