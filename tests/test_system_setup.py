import pytest

from mother.app import create_app
from mother.file_tools import FileTools
from mother.providers import ProviderError


def test_registry_migration_and_project_membership(tmp_path):
    app = create_app(tmp_path / "data")
    c = app.test_client()
    system = c.get("/api/system/settings").json
    original = c.get("/api/settings?project_id=mother").json
    assert all(p.get("system_model_id") for p in original["models"])
    assert (tmp_path / "data/config.pre-system.json").exists()
    model = app.extensions["mother_config"].profile("new", "New model", "demo", "simulated", "default soul")
    system["models"].append(model)
    assert c.put("/api/system/settings", json=system).status_code == 200
    assert "new" not in [p["id"] for p in c.get("/api/settings?project_id=mother").json["models"]]
    original["models"].append({**model, "system_model_id": "new", "soul": "project soul"})
    assert c.put("/api/settings?project_id=mother", json=original).status_code == 200
    assert "new" not in [p["id"] for p in c.get("/api/settings").json["models"]]
    system["models"][-1]["model"] = "updated"
    assert c.put("/api/system/settings", json=system).status_code == 200
    saved = c.get("/api/settings?project_id=mother").json
    assert saved["models"][-1]["model"] == "updated"
    assert saved["models"][-1]["soul"] == "project soul"
    saved["models"].pop()
    assert c.put("/api/settings?project_id=mother", json=saved).status_code == 200
    assert c.get("/api/system/settings").json["models"][-1]["id"] == "new"
    assert create_app(tmp_path / "data").test_client().get("/api/system/settings").json["models"][-1]["id"] == "new"


def test_removing_a_system_model_removes_it_from_every_project(tmp_path):
    app = create_app(tmp_path / "data")
    c = app.test_client()
    stale = c.get("/api/settings").json
    system = c.get("/api/system/settings").json
    removed = system["models"].pop(0)
    system["chief_id"] = ""
    assert c.put("/api/system/settings", json=system).status_code == 200
    for pid in ("default", "mother"):
        models = c.get(f"/api/settings?project_id={pid}").json["models"]
        assert removed["id"] not in [p.get("system_model_id") for p in models]
    # A browser tab opened before the deletion cannot put the model back.
    assert c.put("/api/settings", json=stale).status_code == 400
    assert removed["id"] not in [p.get("system_model_id") for p in c.get("/api/settings").json["models"]]
    cid = c.post("/api/conversations", json={}).json["id"]
    assert c.post(f"/api/conversations/{cid}/messages", json={"content": f"@{removed['id']} hello", "mode": "broadcast"}).status_code == 400


def test_system_rename_reaches_projects_unless_the_project_set_its_own_name(tmp_path):
    app = create_app(tmp_path / "data")
    c = app.test_client()
    system = c.get("/api/system/settings").json
    follower, aliased = system["models"][0]["id"], system["models"][1]["id"]
    project = c.get("/api/settings?project_id=mother").json
    next(p for p in project["models"] if p["system_model_id"] == aliased)["name"] = "My nickname"
    assert c.put("/api/settings?project_id=mother", json=project).status_code == 200
    for model in system["models"]:
        model["name"] = "System " + model["id"]
    assert c.put("/api/system/settings", json=system).status_code == 200
    names = {p["system_model_id"]: p["name"] for p in c.get("/api/settings?project_id=mother").json["models"]}
    assert names[follower] == "System " + follower
    assert names[aliased] == "My nickname"
    # The untouched project follows the registry for both.
    other = {p["system_model_id"]: p["name"] for p in c.get("/api/settings?project_id=default").json["models"]}
    assert other[aliased] == "System " + aliased


def test_shared_roots_are_system_owned_and_available_in_other_projects(tmp_path):
    app = create_app(tmp_path / "data")
    c = app.test_client()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("Shared guide", encoding="utf-8")
    system = c.get("/api/system/settings").json
    system["shared_paths"] = {"docs": str(docs), "tools": ""}
    assert c.put("/api/system/settings", json=system).status_code == 200
    project = c.get("/api/settings?project_id=mother").json
    assert FileTools(project, {}).execute("read_file", {"path": "/docs/guide.md"})["content"] == "Shared guide"
    project["shared_paths"]["docs"] = str(tmp_path)
    c.put("/api/settings?project_id=mother", json=project)
    assert c.get("/api/settings?project_id=mother").json["shared_paths"]["docs"] == str(docs)


def test_file_access_is_bounded_and_selected_files_remain_private(tmp_path):
    (tmp_path / "one.md").write_text("one")
    (tmp_path / "two.md").write_text("two")
    (tmp_path / ".env").write_text("SECRET")
    settings = {"project_path": str(tmp_path), "context_files": ["one.md", "two.md"], "shared_paths": {"docs": str(tmp_path)}, "max_context_chars": 5}
    runtime = FileTools(settings, {"context_mode": "files", "context_files": ["one.md"]})
    assert [f["path"] for f in runtime.execute("list_files", {"folder": "/project"})["files"]] == ["/project/one.md"]
    for path in ("/project/two.md", "/docs/../one.md", "/docs/.env", "C:/one.md", "/other/one.md", "/docs/one.md:stream"):
        with pytest.raises(ProviderError):
            runtime.execute("read_file", {"path": path})
    assert runtime.execute("read_file", {"path": "/project/one.md"})["content"] == "one"
    with pytest.raises(ProviderError, match="context limit"):
        runtime.execute("read_file", {"path": "/docs/two.md"})
