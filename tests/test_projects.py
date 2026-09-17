import json
import sqlite3
import time
from pathlib import Path

import pytest

from mother.app import create_app
from mother.search import SearchService, DIMENSIONS


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path / "data")
    cfg = app.extensions["mother_config"]
    settings = cfg.read()
    settings["models"] = [cfg.profile("chief", "Default voice", "demo", "simulated", "Be clear")]
    cfg.save(settings)
    return app


def create_project(client, name="Research notes", kind="research"):
    response = client.post("/api/projects", json={"name": name, "type": kind})
    assert response.status_code == 201
    return response.json


def test_project_folders_settings_and_restart(app):
    client = app.test_client()
    project = create_project(client)
    pid = project["id"]
    folder = Path(project["storage_path"])
    assert all((folder / name).is_dir() for name in ("workspace", "conversations", "attachments"))
    settings = client.get(f"/api/settings?project_id={pid}").json
    assert settings["project_path"] == str(folder / "workspace")
    assert settings["context_files"] == []
    settings["models"][0]["name"] = "Research voice"
    assert client.put(f"/api/settings?project_id={pid}", json=settings).status_code == 200
    assert client.get("/api/settings").json["models"][0]["name"] == "Default voice"
    assert json.loads((folder / "config.json").read_text())["models"][0]["name"] == "Research voice"
    cid = client.post(f"/api/conversations?project_id={pid}", json={"title": "Research stack"}).json["id"]
    store = app.extensions["store"]
    event = store.add(cid, "user", "You", "Research evidence")
    assert json.loads(next((folder / "conversations").rglob("*.jsonl")).read_text())["id"] == event["id"]
    changed = client.put(f"/api/projects/{pid}", json={"name": "Renamed", "type": "writing"})
    assert changed.json["storage_path"] == project["storage_path"]
    reopened = create_app(store.root).test_client()
    assert reopened.get(f"/api/settings?project_id={pid}").json["models"][0]["name"] == "Research voice"
    assert reopened.get(f"/api/conversations?project_id={pid}").json[0]["id"] == cid
    assert next(p for p in reopened.get("/api/projects").json["projects"] if p["id"] == pid)["type"] == "writing"


def test_conversations_search_trash_and_scope_are_isolated(app):
    c = app.test_client()
    pid = create_project(c)["id"]
    own = c.post(f"/api/conversations?project_id={pid}", json={"title": "Own"}).json["id"]
    other = c.post("/api/conversations", json={"title": "Other"}).json["id"]
    store = app.extensions["store"]
    for cid in (own, other):
        store.add(cid, "user", "You", "Shared keyword")
    assert [r["id"] for r in c.get(f"/api/conversations?project_id={pid}").json] == [own]
    for endpoint in ("/api/search?q=keyword", "/api/search/hybrid?mode=keyword&q=keyword"):
        result = c.get(endpoint + f"&project_id={pid}").json
        rows = result["results"] if isinstance(result, dict) else result
        assert [r["conversation_id"] for r in rows] == [own]
    assert c.get(f"/api/conversations/{other}?project_id={pid}").status_code == 404
    assert c.delete(f"/api/conversations/{other}?project_id={pid}", json={}).status_code == 404
    assert c.post(f"/api/conversations/{other}/messages?project_id={pid}", json={"content": "Wrong project"}).status_code == 404
    assert c.delete(f"/api/conversations/{own}?project_id={pid}", json={}).status_code == 200
    assert c.get("/api/trash").json == []
    assert c.get(f"/api/trash?project_id={pid}").json[0]["id"] == own
    assert c.post(f"/api/conversations/{own}/restore?project_id=default", json={}).status_code == 404
    assert c.post(f"/api/conversations/{own}/restore?project_id={pid}", json={}).status_code == 200


def test_run_uses_owning_project_configuration_and_history(app, monkeypatch):
    from mother import providers
    c = app.test_client()
    pid = create_project(c)["id"]
    cfg = app.extensions["projects"].config(pid)
    settings = cfg.read()
    settings["models"][0].update(id="research", name="Research voice", soul="Research soul")
    settings["chief_id"] = "research"
    cfg.save(settings)
    cid = c.post(f"/api/conversations?project_id={pid}", json={}).json["id"]
    other = c.post("/api/conversations", json={}).json["id"]
    store = app.extensions["store"]
    store.add(other, "user", "You", "PRIVATE_OTHER_HISTORY")
    calls = []
    def complete(profile, system, prompt, key, images, **kwargs):
        calls.append((profile, system, prompt))
        return {"text": "Research reply", "usage": {}}
    monkeypatch.setattr(providers, "complete", complete)
    # Even an old unscoped conversation URL resolves its owning project's settings.
    response = c.post(f"/api/conversations/{cid}/messages", json={"content": "Own question"})
    assert response.status_code == 202
    deadline = time.monotonic() + 5
    while store.run(response.json["id"])["status"] == "running" and time.monotonic() < deadline:
        time.sleep(.02)
    assert store.run(response.json["id"])["status"] == "completed"
    assert calls[0][0]["id"] == "research"
    assert "Research soul" in calls[0][1]
    assert "PRIVATE_OTHER_HISTORY" not in calls[0][2]
    assert c.put(f"/api/conversations/{cid}/models/research/squelch?project_id={pid}", json={"squelched": True}).status_code == 200
    assert store.participation(other) == []


def test_legacy_data_migrates_without_changing_config_or_mirrors(tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    with sqlite3.connect(root / "mother.db") as db:
        db.execute("CREATE TABLE conversations(id TEXT PRIMARY KEY,title TEXT NOT NULL,created_at TEXT NOT NULL)")
        db.execute("INSERT INTO conversations VALUES ('old','Old chat','2026-01-01')")
    app = create_app(root)
    c = app.test_client()
    assert c.get("/api/conversations").json[0]["project_id"] == "default"
    app.extensions["store"].add("old", "user", "You", "Still here")
    assert list((root / "conversations").rglob("old.jsonl"))
    assert create_app(root).test_client().get("/api/conversations").json[0]["id"] == "old"


@pytest.mark.parametrize("data", [{"name": ""}, {"name": "x", "type": "../outside"}, {"name": "x" * 101}, {"name": 12}])
def test_invalid_projects_do_not_create_rows(app, data):
    c = app.test_client()
    assert c.post("/api/projects", json=data).status_code == 400
    assert len(c.get("/api/projects").json["projects"]) == 2
    assert c.get("/api/settings?project_id=missing").status_code == 404


def test_semantic_project_filter_applies_before_limit(app):
    c = app.test_client()
    pid = create_project(c)["id"]
    store = app.extensions["store"]
    own = store.create_conversation("Own", pid)["id"]
    other = store.create_conversation("Other")["id"]
    class Embedder:
        def embed(self, texts, query=False):
            return [[1.0] + [0.0] * (DIMENSIONS - 1) for _ in texts]
    service = SearchService(store, Embedder())
    kept = store.add(own, "user", "You", "Unique evidence")
    # Fill the nearest-neighbor limit with another project's messages.
    for i in range(201):
        store.add(other, "user", "You", f"Other evidence {i}")
    service.process_pending()
    assert [r["id"] for r in service.semantic("evidence", project_id=pid)] == [kept["id"]]
    assert [r["id"] for r in service.fulltext("evidence", project_id=pid)] == [kept["id"]]
    assert [r["id"] for r in service.search("evidence", project_id=pid)["results"]] == [kept["id"]]
    assert service.semantic("evidence", cid=other, project_id=pid) == []
    status = service.status(pid)
    assert status["total"] == status["indexed"] == status["chunks"] == 1


def test_mother_main_project_bootstraps_repository_documents_once(app):
    from mother import workspace
    c = app.test_client()
    listing = c.get("/api/projects").json
    assert listing["default_project_id"] == "mother"
    main = listing["projects"][0]
    assert main["id"] == "mother" and main["is_main"] and main["type"] == "coding"
    assert main["documents"][0]["path"] == "docs/MOTHER_KNOWLEDGE_MODEL_ARCHITECTURE.md"
    cfg = c.get("/api/settings?project_id=mother").json
    assert cfg["project_path"] == main["workspace_path"]
    code, manifests = workspace.model_snapshots(cfg, cfg["models"])
    assert all("Knowledge Bus" in content for content in code.values())
    doc = c.get("/api/projects/mother/documents/architecture?project_id=mother")
    assert doc.status_code == 200 and "# 35. Core Principle" in doc.json["content"]
    assert c.get("/api/projects/mother/documents/review?project_id=mother").status_code == 200
    assert c.get("/api/projects/mother/documents/architecture?project_id=default").status_code == 404
    assert c.get("/api/projects/default/documents/architecture?project_id=default").status_code == 400
    assert c.put("/api/projects/mother", json={"name": "General", "type": "general"}).status_code == 400
    cfg["context_files"] = []
    cfg["models"][0]["name"] = "My Mother architect"
    assert c.put("/api/settings?project_id=mother", json=cfg).status_code == 200
    cid = c.post("/api/conversations?project_id=mother", json={"title": "Mother development"}).json["id"]
    assert c.get("/api/conversations?project_id=default").json == []
    reopened = create_app(app.extensions["store"].root).test_client()
    assert len(reopened.get("/api/projects").json["projects"]) == 2
    saved = reopened.get("/api/settings?project_id=mother").json
    assert saved["models"][0]["name"] == "My Mother architect" and saved["context_files"] == []
    assert reopened.get("/api/conversations?project_id=mother").json[0]["id"] == cid
    assert reopened.get("/api/settings?project_id=default").json["models"][0]["name"] == "Default voice"


def test_projects_created_from_mother_do_not_inherit_its_documents(app):
    c = app.test_client()
    result = c.post("/api/projects?project_id=mother", json={"name": "Unrelated research", "type": "research"})
    assert result.status_code == 201
    project = result.json
    assert not project["is_main"] and project["documents"] == []
    cfg = c.get(f"/api/settings?project_id={project['id']}").json
    assert cfg["context_files"] == []
    assert cfg["project_path"] == project["workspace_path"]


def test_deleted_project_is_hidden_kept_and_restorable(app):
    c = app.test_client()
    project = create_project(c)
    pid = project["id"]
    cid = c.post(f"/api/conversations?project_id={pid}", json={"title": "Keep me"}).json["id"]
    ids = lambda: [p["id"] for p in c.get("/api/projects").json["projects"]]
    for builtin in ("mother", "default"):
        assert c.delete(f"/api/projects/{builtin}", json={}).status_code == 400
    assert c.delete(f"/api/projects/{pid}", json={}).status_code == 200
    assert pid not in ids()
    assert c.get(f"/api/conversations?project_id={pid}").status_code == 404
    assert Path(project["storage_path"]).is_dir()
    assert [p["id"] for p in c.get("/api/projects/deleted").json] == [pid]
    assert c.delete(f"/api/projects/{pid}", json={}).status_code == 404
    # Survives a restart, then comes back with its conversations.
    reopened = create_app(app.extensions["store"].root).test_client()
    assert pid not in [p["id"] for p in reopened.get("/api/projects").json["projects"]]
    assert reopened.post(f"/api/projects/{pid}/restore", json={}).json["name"] == "Research notes"
    assert pid in ids()
    assert c.get("/api/projects/deleted").json == []
    assert [r["id"] for r in c.get(f"/api/conversations?project_id={pid}").json] == [cid]


def test_project_with_a_running_reply_cannot_be_deleted(app):
    c = app.test_client()
    pid = create_project(c)["id"]
    cid = c.post(f"/api/conversations?project_id={pid}", json={"title": "Busy"}).json["id"]
    with app.extensions["store"].connect() as db:
        db.execute("INSERT INTO runs (id,conversation_id,status,created_at) VALUES ('r1',?,'running','now')", (cid,))
    assert c.delete(f"/api/projects/{pid}", json={}).status_code == 400
    assert pid in [p["id"] for p in c.get("/api/projects").json["projects"]]
