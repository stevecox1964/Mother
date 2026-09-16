"""Local hybrid conversation search, adapted from BookMarkManager's sqlite-vec index."""

from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import math
import re
import threading

import requests
from sqlite_vec import serialize_float32

MODEL = "nomic-embed-text:v1.5"
DIMENSIONS = 768
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200
SIGNATURE = f"ollama:{MODEL}:{DIMENSIONS}:chunks-{CHUNK_SIZE}-{CHUNK_OVERLAP}:prefix-v1"
SEARCH_KINDS = "'user','reply','contribution','synthesis'"


def initialize_index(db):
    db.executescript(f"""
        CREATE TABLE IF NOT EXISTS search_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS indexed_events (
            event_id TEXT PRIMARY KEY REFERENCES events(id), content_hash TEXT NOT NULL,
            signature TEXT NOT NULL, indexed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS message_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL REFERENCES events(id),
            chunk_index INTEGER NOT NULL, content TEXT NOT NULL, UNIQUE(event_id, chunk_index));
        CREATE TABLE IF NOT EXISTS embedding_jobs (
            event_id TEXT PRIMARY KEY REFERENCES events(id), error TEXT, attempts INTEGER NOT NULL DEFAULT 0);
        CREATE VIRTUAL TABLE IF NOT EXISTS message_vectors USING vec0(
            chunk_id INTEGER PRIMARY KEY, embedding float[{DIMENSIONS}] distance_metric=cosine,
            conversation_id TEXT, day TEXT, active INTEGER);
        CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(content, tokenize='unicode61');
        CREATE TRIGGER IF NOT EXISTS queue_search_message AFTER INSERT ON events
            WHEN NEW.kind IN ({SEARCH_KINDS}) AND length(trim(NEW.content)) > 0
            BEGIN
                INSERT INTO message_fts(rowid, content) VALUES (NEW.seq, NEW.content);
                INSERT OR IGNORE INTO embedding_jobs(event_id) VALUES (NEW.id);
            END;
    """)
    db.execute(
        "INSERT OR IGNORE INTO search_metadata VALUES ('signature', ?)", (SIGNATURE,)
    )
    # Backfill derived text search and durable embedding work for existing archives.
    db.execute(f"""INSERT INTO message_fts(rowid,content)
        SELECT seq,content FROM events WHERE kind IN ({SEARCH_KINDS}) AND length(trim(content))>0
        AND seq NOT IN (SELECT rowid FROM message_fts)""")
    db.execute(f"""INSERT OR IGNORE INTO embedding_jobs(event_id)
        SELECT id FROM events WHERE kind IN ({SEARCH_KINDS}) AND length(trim(content))>0
        AND id NOT IN (SELECT event_id FROM indexed_events)""")


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Keep the reference project's overlap and sentence-boundary approach."""
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Chunk overlap must be smaller than the chunk size.")
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            search_start = start + max(overlap + 1, int(size * 0.8))
            breaks = [
                text.rfind(sep, search_start, end) for sep in (". ", "! ", "? ", "\n")
            ]
            boundary = max(breaks)
            if boundary >= search_start:
                end = boundary + 1
        content = text[start:end].strip()
        if content:
            chunks.append(content)
        if end == len(text):
            break
        start = end - overlap
    return chunks


class EmbeddingError(RuntimeError):
    pass


class LocalEmbedder:
    def embed(self, texts, query=False):
        prefix = "search_query: " if query else "search_document: "
        try:
            response = requests.post(
                "http://127.0.0.1:11434/api/embed",
                json={
                    "model": MODEL,
                    "input": [prefix + text for text in texts],
                    "truncate": False,
                    "keep_alive": "5m",
                },
                timeout=(3, 60),
            )
            if response.status_code == 404:
                raise EmbeddingError(
                    f"Install the local search model with: ollama pull {MODEL}"
                )
            if not response.ok:
                raise EmbeddingError(
                    f"Local search model returned HTTP {response.status_code}. Exact text search is still available."
                )
            vectors = response.json().get("embeddings")
            return validate_vectors(vectors, len(texts))
        except requests.RequestException:
            raise EmbeddingError(
                "Local search is unavailable. Start Ollama, then retry indexing. Exact text search still works."
            ) from None
        except (ValueError, TypeError, KeyError):
            raise EmbeddingError(
                "The local search model returned invalid embeddings."
            ) from None


def validate_vectors(vectors, expected):
    if not isinstance(vectors, list) or len(vectors) != expected:
        raise EmbeddingError(
            "The local search model returned an incomplete embedding batch."
        )
    normalized = []
    for vector in vectors:
        if not isinstance(vector, (list, tuple)) or len(vector) != DIMENSIONS:
            raise EmbeddingError(
                "The local search model returned the wrong vector dimensions."
            )
        if any(
            isinstance(x, bool)
            or not isinstance(x, (float, int))
            or not math.isfinite(x)
            for x in vector
        ):
            raise EmbeddingError(
                "The local search model returned invalid vector values."
            )
        norm = math.sqrt(sum(x * x for x in vector))
        if not math.isfinite(norm) or norm == 0:
            raise EmbeddingError(
                "The local search model returned an invalid zero vector."
            )
        normalized.append([x / norm for x in vector])
    return normalized


class SearchService:
    def __init__(self, store, embedder=None):
        self.store = store
        self.embedder = embedder or LocalEmbedder()
        self.index_lock = threading.Lock()
        self.embed_lock = threading.Lock()
        self.wakeup = threading.Event()
        self.stopping = threading.Event()
        self.worker = None
        self.busy = False
        self.last_error = ""
        self.query_vector = lru_cache(maxsize=64)(self._query_vector)

    def _check_signature(self):
        with self.store.connect() as db:
            signature = db.execute(
                "SELECT value FROM search_metadata WHERE key='signature'"
            ).fetchone()[0]
        if signature != SIGNATURE:
            raise EmbeddingError(
                "The search model changed. Rebuild the derived index before using semantic search."
            )

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        self.worker = threading.Thread(
            target=self._work, name="mother-search-index", daemon=True
        )
        self.worker.start()
        self.wake()

    def wake(self):
        self.wakeup.set()

    def stop(self):
        self.stopping.set()
        self.wake()

    def _work(self):
        while not self.stopping.is_set():
            self.wakeup.wait()
            self.wakeup.clear()
            if not self.stopping.is_set() and not self.last_error:
                self.process_pending()

    def retry(self):
        with self.store.connect() as db:
            db.execute("UPDATE embedding_jobs SET error=NULL")
        self.last_error = ""
        self.start()
        self.wake()

    def status(self, project_id=""):
        with self.store.connect() as db:
            counts = db.execute(f"""SELECT COUNT(*) total, COUNT(i.event_id) indexed_count
                FROM events e JOIN conversations c ON c.id=e.conversation_id
                LEFT JOIN indexed_events i ON i.event_id=e.id
                WHERE c.deleted_at IS NULL AND e.kind IN ({SEARCH_KINDS}) AND length(trim(e.content))>0
                AND (?='' OR c.project_id=?)""", (project_id, project_id)).fetchone()
            failed = db.execute("""SELECT COUNT(*) FROM embedding_jobs j JOIN events e ON e.id=j.event_id
                JOIN conversations c ON c.id=e.conversation_id WHERE c.deleted_at IS NULL AND j.error IS NOT NULL
                AND (?='' OR c.project_id=?)""", (project_id, project_id)).fetchone()[
                0
            ]
            chunks = db.execute(
                """SELECT COUNT(*) FROM message_chunks mc JOIN events e ON e.id=mc.event_id
                JOIN conversations c ON c.id=e.conversation_id WHERE c.deleted_at IS NULL
                AND (?='' OR c.project_id=?)""", (project_id, project_id)
            ).fetchone()[0]
        return dict(
            total=counts["total"],
            indexed=counts["indexed_count"],
            pending=counts["total"] - counts["indexed_count"],
            failed=failed,
            chunks=chunks,
            busy=self.busy,
            error=self.last_error,
            model=MODEL,
            local=True,
        )

    def process_pending(self):
        if not self.index_lock.acquire(blocking=False):
            return
        self.busy = True
        try:
            self._check_signature()
            while not self.stopping.is_set():
                with self.store.connect() as db:
                    row = db.execute("""SELECT e.* FROM embedding_jobs j JOIN events e ON e.id=j.event_id
                        JOIN conversations c ON c.id=e.conversation_id WHERE j.error IS NULL AND c.deleted_at IS NULL
                        ORDER BY e.seq LIMIT 1""").fetchone()
                if row is None:
                    break
                try:
                    self.index_event(dict(row))
                except Exception as exc:
                    message = (
                        str(exc)
                        if isinstance(exc, EmbeddingError)
                        else "Search indexing failed. Retry indexing; your messages are saved."
                    )
                    with self.store.connect() as db:
                        db.execute(
                            "UPDATE embedding_jobs SET error=?, attempts=attempts+1 WHERE event_id=?",
                            (message, row["id"]),
                        )
                    self.last_error = message
                    break  # No retry loop or repeated model calls during an outage.
        except EmbeddingError as exc:
            self.last_error = str(exc)
        finally:
            self.busy = False
            self.index_lock.release()

    def index_event(self, event):
        chunks = chunk_text(event["content"])
        vectors = []
        for offset in range(0, len(chunks), 16):
            with self.embed_lock:
                batch = self.embedder.embed(chunks[offset : offset + 16])
            vectors.extend(validate_vectors(batch, len(chunks[offset : offset + 16])))
        # Commit a complete event atomically. Never keep half of an embedding batch.
        with self.store.lock, self.store.connect() as db:
            active = int(
                db.execute(
                    "SELECT deleted_at IS NULL FROM conversations WHERE id=?",
                    (event["conversation_id"],),
                ).fetchone()[0]
            )
            ids = db.execute(
                "SELECT id FROM message_chunks WHERE event_id=?", (event["id"],)
            ).fetchall()
            for row in ids:
                db.execute("DELETE FROM message_vectors WHERE chunk_id=?", (row["id"],))
            db.execute("DELETE FROM message_chunks WHERE event_id=?", (event["id"],))
            for index, (text, vector) in enumerate(zip(chunks, vectors)):
                chunk_id = db.execute(
                    "INSERT INTO message_chunks(event_id,chunk_index,content) VALUES (?,?,?)",
                    (event["id"], index, text),
                ).lastrowid
                db.execute(
                    "INSERT INTO message_vectors(chunk_id,embedding,conversation_id,day,active) VALUES (?,?,?,?,?)",
                    (
                        chunk_id,
                        serialize_float32(vector),
                        event["conversation_id"],
                        event["created_at"][:10],
                        active,
                    ),
                )
            db.execute(
                "INSERT OR REPLACE INTO indexed_events VALUES (?,?,?,?)",
                (
                    event["id"],
                    hashlib.sha256(event["content"].encode()).hexdigest(),
                    SIGNATURE,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            db.execute("DELETE FROM embedding_jobs WHERE event_id=?", (event["id"],))

    def _query_vector(self, text):
        with self.embed_lock:
            return serialize_float32(
                validate_vectors(self.embedder.embed([text], query=True), 1)[0]
            )

    def semantic(self, query, start="", end="", cid="", project_id=""):
        if cid and project_id and self.store.conversation_project(cid) != project_id:
            return []
        self._check_signature()
        vector = self.query_vector(query)
        filters, args = ["embedding MATCH ?", "k = ?", "active = 1"], [vector, 200]
        for column, operator, value in (
            ("day", ">=", start),
            ("day", "<=", end),
            ("conversation_id", "=", cid),
        ):
            if value:
                filters.append(f"{column} {operator} ?")
                args.append(value)
        if project_id and not cid:
            filters.append("conversation_id IN (SELECT id FROM conversations WHERE project_id=?)")
            args.append(project_id)
        with self.store.connect() as db:
            rows = db.execute(
                f"""WITH nearest AS (
                SELECT chunk_id,distance FROM message_vectors WHERE {" AND ".join(filters)} ORDER BY distance)
                SELECT e.*,c.title,mc.content snippet,n.distance FROM nearest n
                JOIN message_chunks mc ON mc.id=n.chunk_id JOIN events e ON e.id=mc.event_id
                JOIN conversations c ON c.id=e.conversation_id WHERE c.deleted_at IS NULL
                ORDER BY n.distance,e.seq DESC""",
                args,
            ).fetchall()
        result, seen = [], set()
        for row in rows:
            if row["id"] not in seen:
                seen.add(row["id"])
                result.append(self.store.decode(row))
        return result

    def fulltext(self, query, start="", end="", cid="", project_id=""):
        tokens = re.findall(r"\w+", query, re.UNICODE)[:24]
        if not tokens:
            return []
        expression = " OR ".join(
            '"' + token.replace('"', '""') + '"' for token in tokens
        )
        with self.store.connect() as db:
            rows = db.execute(
                """SELECT e.*,c.title FROM message_fts f JOIN events e ON e.seq=f.rowid
                JOIN conversations c ON c.id=e.conversation_id WHERE message_fts MATCH ? AND c.deleted_at IS NULL
                AND (?='' OR substr(e.created_at,1,10)>=?) AND (?='' OR substr(e.created_at,1,10)<=?)
                AND (?='' OR e.conversation_id=?) AND (?='' OR c.project_id=?)
                ORDER BY bm25(message_fts),e.seq DESC LIMIT 200""",
                (expression, start, start, end, end, cid, cid, project_id, project_id),
            ).fetchall()
        return [self.store.decode(row) for row in rows]

    def search(self, query, start="", end="", cid="", mode="hybrid", project_id=""):
        query = query.strip()
        if mode not in ("hybrid", "keyword"):
            raise ValueError("Unknown search mode.")
        if len(query) > 1000:
            raise ValueError("Search query must be at most 1,000 characters.")
        exact = [
            e
            for e in self.store.search(query, start, end, cid, project_id)
            if e["kind"] in ("user", "reply", "contribution", "synthesis")
        ]
        status = self.status(project_id)
        if not query or mode == "keyword":
            return dict(results=exact, warning="", index=status)
        lexical = {e["id"]: e for e in exact}
        for event in self.fulltext(query, start, end, cid, project_id):
            lexical.setdefault(event["id"], event)
        semantic, warning = [], ""
        if status["indexed"]:
            try:
                semantic = self.semantic(query, start, end, cid, project_id)
            except EmbeddingError as exc:
                warning = str(exc)
        elif status["total"]:
            warning = (
                status["error"]
                or "Search is indexing your conversations. Showing text matches for now."
            )
        # Reciprocal-rank fusion preserves exact matches alongside semantic neighbors.
        scores, found, types = {}, {}, {}
        for name, ranked in (("text", list(lexical.values())), ("meaning", semantic)):
            for rank, event in enumerate(ranked, 1):
                eid = event["id"]
                scores[eid] = scores.get(eid, 0) + 1 / (60 + rank)
                found[eid] = {**found.get(eid, {}), **event}
                types.setdefault(eid, []).append(name)
        ordered = sorted(scores, key=lambda eid: (-scores[eid], -found[eid]["seq"]))[
            :200
        ]
        return dict(
            results=[
                {**found[eid], "match_type": " + ".join(types[eid])} for eid in ordered
            ],
            warning=warning,
            index=status,
        )
