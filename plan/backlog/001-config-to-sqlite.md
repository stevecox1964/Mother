# 001 — Move model and project configuration into SQLite

**Priority:** P1
**Status:** open
**Added:** 2026-09-11
**Closed:** _Not yet._

## Why

Conversations already live in SQLite. `data/mother.db` holds `projects`, `conversations`, `events`, `runs`, `participation` and `run_members`, plus the search tables `message_fts` (FTS5), `message_vectors` (sqlite-vec), `message_chunks`, `indexed_events` and `embedding_jobs`. That half is done.

Configuration did not follow. Model profiles, project bindings, selected files and the machine-wide model registry are JSON files:

```
data/config.json                    # Default project
data/projects/<id>/config.json      # each project
data/system/config.json             # machine-wide model registry
```

This split caused two real bugs on 2026-09-11. Renaming or deleting a model in System setup left stale copies in every project, because each project config held its own duplicate of the name and the binding. The fix works, but it is hand-written propagation across files (`SystemConfig.save_system` walks every project config and rewrites it) instead of a foreign key.

Consequences that remain:

- Every cross-file change needs its own propagation code, and each one can be forgotten.
- Writes are whole-file replacements under a process-local `threading.RLock`. Two processes on the same data directory can lose each other's writes. SQLite in WAL mode already solves this for conversations.
- Config cannot be joined against conversations, runs or search results in one query.
- Repairs need one-time migration passes plus `.pre-*.json` backup files. There are already three generations of those on disk.

The user also has other projects on this same JSON-config pattern, so the shape of the fix is worth getting right once.

## What "done" looks like

- Model profiles, the system registry, project bindings, selected context files and shared folder paths live in tables in `data/mother.db`.
- Deleting a system model removes its project bindings through a foreign key or a single delete, not by walking every project file.
- Renaming a system model needs no propagation step. A project reads the registry name through a join unless it stores its own alias.
- Credentials stay out of the database. They remain in `data/.env` and process environment variables.
- Existing JSON configs are imported once on first start, with the originals preserved on disk.
- All 110 backend tests still pass, plus new tests for: import from JSON, concurrent writes from two connections, deleting a system model in use, and project isolation.
- `GET /api/settings`, `PUT /api/settings`, `GET/PUT /api/system/settings` keep their current request and response shapes so the frontend needs no change.

## Where to start

- `backend/mother/config.py` — `Config` owns read, validate and whole-file save. The validation in `Config.save` is the part worth keeping; the file I/O at the end of it is the part to replace.
- `backend/mother/system_config.py` — `SystemConfig` holds the registry, `resolve()` overlays connection fields onto project profiles, `save_system()` propagates renames and deletions, `adopt_registry_names()` is a one-time repair. Most of this becomes a query.
- `backend/mother/projects.py` — `Projects` caches one `Config` per project id and creates project folders.
- `backend/mother/store.py` — the existing schema and connection handling. Follow its WAL setup and `connect()` pattern rather than opening a second database.
- `backend/mother/app.py:27` — `Config(store.root)` is where the Default project config is constructed.
- Read `docs/MOTHER_ARCHITECTURE_REVIEW.md` first. Its recommended sequence puts a project-scoped knowledge store next, and that store will want the same tables.

## Watch out for

- **Preserve `data/`.** It holds the live database, conversation mirrors, attachments and credentials.
- **Credentials must never enter the database or a snapshot.** `Config.public()` already strips them; keep that boundary.
- **Souls, expertise and file assignments are per project and must not be flattened into the registry.** Several profiles can share one connection with different souls. The Demo profiles already do this.
- **`name_alias` semantics.** An empty alias means "follow the registry name". Tests `test_system_rename_reaches_projects_unless_the_project_set_its_own_name` and `test_removing_a_system_model_removes_it_from_every_project` in `tests/test_system_setup.py` encode this.
- **Three generations of migration already ran** and left `config.pre-system.json` and `config.pre-names.json` beside the configs. The importer must be idempotent and must not re-import from a backup file.
- **Run one backend per data directory.** `MOTHER_DATA_DIR` selects isolated storage and `MOTHER_PORT` changes the port. Use those to test rather than touching the live directory.
