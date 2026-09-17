import json
import os
import sqlite3
import threading
import uuid
import sqlite_vec
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def uid():
    return uuid.uuid4().hex


class Store:
    """SQLite is authoritative; dated JSONL files are atomically rebuilt mirrors."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.on_search_change = lambda: None
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    created_at TEXT NOT NULL, kind TEXT NOT NULL, author TEXT NOT NULL,
                    content TEXT NOT NULL, metadata TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS event_time ON events(created_at);
                CREATE INDEX IF NOT EXISTS event_conversation ON events(conversation_id, seq);
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    status TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(conversation_id)
                    WHERE status = 'running';
                CREATE TABLE IF NOT EXISTS participation (
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    model_id TEXT NOT NULL, squelched INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(conversation_id,model_id));
                CREATE TABLE IF NOT EXISTS run_members (
                    run_id TEXT NOT NULL REFERENCES runs(id), model_id TEXT NOT NULL,
                    status TEXT NOT NULL, round INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(run_id,model_id));
            """)
            run_columns = {r[1] for r in db.execute("PRAGMA table_info(runs)")}
            if "mode" not in run_columns:
                db.execute(
                    "ALTER TABLE runs ADD COLUMN mode TEXT NOT NULL DEFAULT 'direct'"
                )
            if "rounds" not in run_columns:
                db.execute(
                    "ALTER TABLE runs ADD COLUMN rounds INTEGER NOT NULL DEFAULT 1"
                )
            columns = {
                r["name"] for r in db.execute("PRAGMA table_info(conversations)")
            }
            if "deleted_at" not in columns:
                db.execute("ALTER TABLE conversations ADD COLUMN deleted_at TEXT")
            db.execute(
                "INSERT OR IGNORE INTO projects (id,name,type,created_at) VALUES ('default','Default project','general',?)",
                (now(),),
            )
            if "project_id" not in columns:
                db.execute("ALTER TABLE conversations ADD COLUMN project_id TEXT REFERENCES projects(id)")
                db.execute("UPDATE conversations SET project_id='default' WHERE project_id IS NULL")
            db.execute("CREATE INDEX IF NOT EXISTS conversation_project ON conversations(project_id)")
            if "deleted_at" not in {r["name"] for r in db.execute("PRAGMA table_info(projects)")}:
                db.execute("ALTER TABLE projects ADD COLUMN deleted_at TEXT")
            from .search import initialize_index

            initialize_index(db)
            interrupted = db.execute(
                "SELECT * FROM runs WHERE status='running'"
            ).fetchall()
            db.execute(
                "UPDATE runs SET status='interrupted',finished_at=? WHERE status='running'",
                (now(),),
            )
        for run in interrupted:
            self.add(
                run["conversation_id"],
                "system",
                "Mother",
                "Run interrupted by a server restart. Send another message to continue.",
                {"run_id": run["id"]},
            )
        self.rebuild_mirrors()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "mother.db", timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            db.enable_load_extension(True)
            try:
                sqlite_vec.load(db)
            finally:
                db.enable_load_extension(False)
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def projects(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY created_at,id")]

    def project(self, pid):
        """Deleted projects are hidden everywhere until restored."""
        with self.connect() as db:
            row = db.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (pid,)).fetchone()
            return dict(row) if row else None

    def deleted_projects(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM projects WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC")]

    def delete_project(self, pid):
        with self.lock, self.connect() as db:
            if db.execute(
                "SELECT 1 FROM runs JOIN conversations c ON c.id=runs.conversation_id "
                "WHERE c.project_id=? AND runs.status='running'", (pid,)
            ).fetchone():
                raise ValueError("Wait for the current reply to finish before deleting this project.")
            return db.execute(
                "UPDATE projects SET deleted_at=? WHERE id=? AND deleted_at IS NULL", (now(), pid)
            ).rowcount > 0

    def restore_project(self, pid):
        with self.lock, self.connect() as db:
            return db.execute(
                "UPDATE projects SET deleted_at=NULL WHERE id=? AND deleted_at IS NOT NULL", (pid,)
            ).rowcount > 0

    def conversation_project(self, cid):
        with self.connect() as db:
            row = db.execute("SELECT project_id FROM conversations WHERE id=?", (cid,)).fetchone()
            return row[0] if row else None

    def project_folder(self, pid):
        if not self.project(pid):
            raise ValueError("Project not found.")
        return self.root / "projects" / pid

    def conversations(self, project_id="default"):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute("""SELECT c.*, COUNT(e.seq) message_count,
                COALESCE(MAX(e.created_at),c.created_at) updated_at FROM conversations c
                LEFT JOIN events e ON e.conversation_id=c.id WHERE c.deleted_at IS NULL
                AND c.project_id=? GROUP BY c.id ORDER BY updated_at DESC""", (project_id,))
            ]

    def create_conversation(self, title, project_id="default"):
        row = dict(
            id=uid(),
            title=title.strip()[:160] or "Untitled conversation",
            created_at=now(),
            project_id=project_id,
        )
        with self.connect() as db:
            db.execute(
                "INSERT INTO conversations(id,title,created_at,project_id) VALUES (:id,:title,:created_at,:project_id)",
                row,
            )
        return row

    def exists(self, cid):
        with self.connect() as db:
            return bool(
                db.execute(
                    "SELECT 1 FROM conversations WHERE id=? AND deleted_at IS NULL",
                    (cid,),
                ).fetchone()
            )

    def rename_conversation(self, cid, title):
        with self.lock, self.connect() as db:
            return (
                db.execute(
                    "UPDATE conversations SET title=? WHERE id=? AND deleted_at IS NULL",
                    (title, cid),
                ).rowcount
                > 0
            )

    def delete_conversation(self, cid):
        with self.lock, self.connect() as db:
            if db.execute(
                "SELECT 1 FROM runs WHERE conversation_id=? AND status='running'",
                (cid,),
            ).fetchone():
                raise ValueError(
                    "Stop the current reply before deleting this conversation."
                )
            changed = (
                db.execute(
                    "UPDATE conversations SET deleted_at=? WHERE id=? AND deleted_at IS NULL",
                    (now(), cid),
                ).rowcount
                > 0
            )
            db.execute(
                "UPDATE message_vectors SET active=0 WHERE conversation_id=?", (cid,)
            )
            return changed

    def deleted_conversations(self, project_id="default"):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,title,deleted_at,project_id FROM conversations WHERE deleted_at IS NOT NULL AND project_id=? ORDER BY deleted_at DESC",
                    (project_id,),
                )
            ]

    def restore_conversation(self, cid):
        with self.lock, self.connect() as db:
            changed = (
                db.execute(
                    "UPDATE conversations SET deleted_at=NULL WHERE id=? AND deleted_at IS NOT NULL",
                    (cid,),
                ).rowcount
                > 0
            )
            db.execute(
                "UPDATE message_vectors SET active=1 WHERE conversation_id=?", (cid,)
            )
        if changed:
            self.on_search_change()
        return changed

    def events(self, cid, after=0):
        with self.connect() as db:
            return [
                self.decode(r)
                for r in db.execute(
                    "SELECT * FROM events WHERE conversation_id=? AND seq>? ORDER BY seq",
                    (cid, after),
                )
            ]

    @staticmethod
    def decode(row):
        row = dict(row)
        row["metadata"] = json.loads(row["metadata"])
        return row

    def add(self, cid, kind, author, content, metadata=None):
        with self.lock:
            event = dict(
                id=uid(),
                conversation_id=cid,
                created_at=now(),
                kind=kind,
                author=author,
                content=content,
                metadata=json.dumps(metadata or {}),
            )
            with self.connect() as db:
                cur = db.execute(
                    """INSERT INTO events(id,conversation_id,created_at,kind,author,content,metadata)
                    VALUES (:id,:conversation_id,:created_at,:kind,:author,:content,:metadata)""",
                    event,
                )
                event["seq"] = cur.lastrowid
            self.mirror(cid, event["created_at"][:10])
            self.on_search_change()
            return self.decode(event)

    def mirror(self, cid, day):
        pid = self.conversation_project(cid)
        # Preserve the original default-project mirror location for existing backups.
        base = self.root if pid == "default" else self.project_folder(pid)
        folder = base / "conversations" / day.replace("-", "/")
        folder.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE conversation_id=? AND substr(created_at,1,10)=? ORDER BY seq",
                (cid, day),
            )
            body = "".join(
                json.dumps(self.decode(r), ensure_ascii=False) + "\n" for r in rows
            )
        path = folder / f"{cid}.jsonl"
        temp = path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(path)

    def rebuild_mirrors(self):
        with self.lock, self.connect() as db:
            for cid, day in db.execute(
                "SELECT DISTINCT conversation_id,substr(created_at,1,10) FROM events"
            ):
                self.mirror(cid, day)

    def search(self, query, start="", end="", cid="", project_id=""):
        query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self.connect() as db:
            rows = db.execute(
                """SELECT e.*,c.title FROM events e JOIN conversations c ON c.id=e.conversation_id
                WHERE c.deleted_at IS NULL AND e.kind IN ('user','reply','contribution','synthesis')
                AND e.content LIKE ? ESCAPE '\\' AND (?='' OR e.created_at>=?)
                AND (?='' OR substr(e.created_at,1,10)<=?) AND (?='' OR e.conversation_id=?)
                AND (?='' OR c.project_id=?)
                ORDER BY e.seq DESC LIMIT 200""",
                (f"%{query}%", start, start, end, end, cid, cid, project_id, project_id),
            )
            return [self.decode(r) for r in rows]

    def start_run(self, cid, mode="direct", rounds=1, members=()):
        row = dict(
            id=uid(),
            conversation_id=cid,
            status="running",
            created_at=now(),
            mode=mode,
            rounds=rounds,
        )
        with self.lock, self.connect() as db:
            if not db.execute(
                "SELECT 1 FROM conversations WHERE id=? AND deleted_at IS NULL", (cid,)
            ).fetchone():
                raise ValueError("Conversation not found.")
            db.execute(
                "INSERT INTO runs(id,conversation_id,status,created_at,mode,rounds) VALUES (:id,:conversation_id,:status,:created_at,:mode,:rounds)",
                row,
            )
            db.executemany(
                "INSERT INTO run_members VALUES (?,?,?,0)",
                [(row["id"], m, "waiting") for m in members],
            )
        return row

    def run(self, rid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
            if not row:
                return None
            run = dict(row)
            run["members"] = [
                dict(r)
                for r in db.execute(
                    "SELECT model_id,status,round FROM run_members WHERE run_id=?", (rid,)
                )
            ]
            return run

    def runs(self, cid):
        with self.connect() as db:
            runs = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM runs WHERE conversation_id=? ORDER BY created_at DESC LIMIT 20",
                    (cid,),
                )
            ]
            for run in runs:
                run["members"] = [
                    dict(r)
                    for r in db.execute(
                        "SELECT model_id,status,round FROM run_members WHERE run_id=?",
                        (run["id"],),
                    )
                ]
            return runs

    def participation(self, cid):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT model_id,squelched,revision FROM participation WHERE conversation_id=?",
                    (cid,),
                )
            ]

    def voice(self, cid, mid):
        with self.connect() as db:
            r = db.execute(
                "SELECT squelched,revision FROM participation WHERE conversation_id=? AND model_id=?",
                (cid, mid),
            ).fetchone()
            return dict(r) if r else {"squelched": 0, "revision": 0}

    def can_speak(self, rid, mid, revision):
        with self.connect() as db:
            return bool(
                db.execute(
                    """SELECT 1 FROM runs r LEFT JOIN participation p
                ON p.conversation_id=r.conversation_id AND p.model_id=?
                WHERE r.id=? AND r.status='running' AND COALESCE(p.squelched,0)=0
                AND COALESCE(p.revision,0)=?""",
                    (mid, rid, revision),
                ).fetchone()
            )

    def set_squelch(self, cid, mid, squelched):
        with self.lock:
            with self.connect() as db:
                db.execute(
                    """INSERT INTO participation VALUES (?,?,?,1)
                    ON CONFLICT(conversation_id,model_id) DO UPDATE SET squelched=excluded.squelched,
                    revision=participation.revision + (participation.squelched != excluded.squelched)""",
                    (cid, mid, int(squelched)),
                )
                db.execute(
                    """UPDATE run_members SET status=? WHERE model_id=? AND run_id IN
                    (SELECT id FROM runs WHERE conversation_id=? AND status='running')""",
                    ("squelched" if squelched else "waiting", mid, cid),
                )
                # When everyone is muted, release the conversation immediately.
                db.execute(
                    """UPDATE runs SET status='squelched',finished_at=? WHERE conversation_id=? AND status='running'
                    AND EXISTS (SELECT 1 FROM run_members m WHERE m.run_id=runs.id)
                    AND NOT EXISTS (SELECT 1 FROM run_members m LEFT JOIN participation p
                        ON p.conversation_id=runs.conversation_id AND p.model_id=m.model_id
                        WHERE m.run_id=runs.id AND COALESCE(p.squelched,0)=0)""",
                    (now(), cid),
                )
            self.add(
                cid,
                "system",
                "Mother",
                f"{mid} was {'squelched' if squelched else 'unsquelched'}.",
                {"model_id": mid, "squelched": squelched},
            )
            return self.participation(cid)

    def member_status(self, rid, mid, revision, status, round_no):
        with self.lock:
            if not self.can_speak(rid, mid, revision):
                return False
            with self.connect() as db:
                db.execute(
                    "UPDATE run_members SET status=?,round=? WHERE run_id=? AND model_id=?",
                    (status, round_no, rid, mid),
                )
            return True

    def publish_reply(self, run, mid, revision, kind, author, content, metadata):
        # Serialize publication with squelch and cancellation; a late HTTP response cannot slip through.
        with self.lock:
            if not self.can_speak(run["id"], mid, revision):
                return False
            self.add(run["conversation_id"], kind, author, content, metadata)
            return True

    def finish(self, rid, status):
        with self.lock, self.connect() as db:
            db.execute(
                "UPDATE runs SET status=?,finished_at=? WHERE id=? AND status='running'",
                (status, now(), rid),
            )
            db.execute(
                "UPDATE run_members SET status=? WHERE run_id=? AND status IN ('waiting','thinking')",
                ("stopped" if status == "cancelled" else "finished", rid),
            )
