"""Project-scoped write tools: hash locks, backups, boundaries and tool lists."""

import hashlib
import threading
import pytest

from mother.config import Config
from mother.file_tools import FileTools
from mother.model_tools import ModelTools
from mother.providers import ProviderError


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src/app.py").write_bytes(b"x = 1\ny = 2\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("guide", encoding="utf-8")
    settings = {"project_path": str(root), "context_files": [], "project_access": "write",
                "shared_paths": {"docs": str(docs)}, "max_context_chars": 80000}
    return root, settings, FileTools(settings, {}, backup_root=tmp_path / "backups")


def test_create_replace_and_backup(project, tmp_path):
    root, _, tools = project
    made = tools.execute("write_file", {"path": "/project/new/notes.md", "content": "hello"})
    assert made["created"] and (root / "new/notes.md").read_text() == "hello"
    assert made["sha256"] == sha("hello")

    old = tools.execute("read_file", {"path": "/project/src/app.py"})
    done = tools.execute("write_file", {"path": "/project/src/app.py", "content": "x = 3\n", "expected_sha256": old["sha256"]})
    assert (root / "src/app.py").read_text() == "x = 3\n" and not done["created"]
    backup = tmp_path / "backups"
    assert [p.read_text() for p in backup.rglob("app.py")] == ["x = 1\ny = 2\n"]
    assert done["backup"].startswith(str(backup))


def test_stale_or_missing_hash_never_overwrites(project):
    root, _, tools = project
    for expected in (None, sha("something else")):
        args = {"path": "/project/src/app.py", "content": "lost"}
        if expected:
            args["expected_sha256"] = expected
        with pytest.raises(ProviderError, match="changed since"):
            tools.execute("write_file", args)
    with pytest.raises(ProviderError, match="does not exist"):
        tools.execute("write_file", {"path": "/project/ghost.md", "content": "x", "expected_sha256": sha("x")})
    assert (root / "src/app.py").read_text() == "x = 1\ny = 2\n" and not (root / "ghost.md").exists()


def test_edit_requires_one_exact_match(project):
    root, _, tools = project
    current = sha("x = 1\ny = 2\n")
    tools.execute("edit_file", {"path": "/project/src/app.py", "old_text": "y = 2", "new_text": "y = 5", "expected_sha256": current})
    assert (root / "src/app.py").read_text() == "x = 1\ny = 5\n"
    current = sha("x = 1\ny = 5\n")
    for old_text, found in (("z = 9", 0), (" = ", 2)):
        with pytest.raises(ProviderError, match=f"found {found}"):
            tools.execute("edit_file", {"path": "/project/src/app.py", "old_text": old_text, "new_text": "q", "expected_sha256": current})
    assert (root / "src/app.py").read_text() == "x = 1\ny = 5\n"


def test_writes_stay_inside_the_project(project, tmp_path):
    root, settings, tools = project
    (root / "data").mkdir()
    blocked = ["/docs/guide.md", "/project/../escape.md", "/project/.env", "/project/data/config.json",
               "/project/.git/config.md", "/project/tool.exe", "C:/escape.md", "/project/a:b.md", "/other/x.md"]
    for path in blocked:
        with pytest.raises(ProviderError):
            tools.execute("write_file", {"path": path, "content": "bad"})
    assert (tmp_path / "docs/guide.md").read_text() == "guide" and not (tmp_path / "escape.md").exists()
    assert not (root / "data/config.json").exists()

    # A docs mount inside the project stays read-only.
    (root / "manual").mkdir()
    inside = FileTools({**settings, "shared_paths": {"docs": str(root / "manual")}}, {}, backup_root=tmp_path / "b")
    with pytest.raises(ProviderError, match="Shared folders"):
        inside.execute("write_file", {"path": "/project/manual/page.md", "content": "bad"})

    for access in ("selected", "read"):
        reader = FileTools({**settings, "project_access": access}, {}, backup_root=tmp_path / "b")
        with pytest.raises(ProviderError, match="read/write"):
            reader.execute("write_file", {"path": "/project/new.md", "content": "bad"})
    with pytest.raises(ProviderError, match="not configured"):
        FileTools(settings, {}).execute("write_file", {"path": "/project/new.md", "content": "bad"})
    assert not (root / "new.md").exists()


def test_concurrent_writers_with_same_hash_only_one_wins(project):
    root, _, tools = project
    current, results = sha("x = 1\ny = 2\n"), []

    def attempt(text):
        try:
            tools.execute("write_file", {"path": "/project/src/app.py", "content": text, "expected_sha256": current})
            results.append(text)
        except ProviderError:
            results.append(None)

    threads = [threading.Thread(target=attempt, args=(f"writer {n}\n",)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    winners = [r for r in results if r]
    assert len(winners) == 1 and (root / "src/app.py").read_text() == winners[0]


def test_search_respects_file_permissions(project):
    root, settings, tools = project
    (root / "src/secret_plan.py").write_text("needle", encoding="utf-8")
    (root / "src/other.py").write_text("needle here", encoding="utf-8")
    assert [m["path"] for m in tools.execute("search_files", {"folder": "/project", "text": "NEEDLE"})["matches"]] == ["/project/src/other.py"]
    limited = FileTools({**settings, "project_access": "selected", "context_files": ["src/app.py"]},
                        {"context_mode": "files", "context_files": ["src/app.py"]})
    assert limited.execute("search_files", {"folder": "/project", "text": "needle"})["matches"] == []
    assert limited.execute("search_files", {"folder": "/project", "text": "y = 2"})["matches"] == [{"path": "/project/src/app.py", "line": 2, "text": "y = 2"}]


def test_project_and_model_tool_lists(tmp_path):
    cfg = Config(tmp_path)
    settings = cfg.read()
    names = lambda s, profile: {t["name"] for t in ModelTools(cfg, s, profile=profile).definitions}
    assert "write_file" not in names({**settings, "project_access": "read"}, {})
    assert {"write_file", "edit_file", "read_file"} <= names({**settings, "project_access": "write"}, {})
    only_read = {**settings, "project_access": "write", "tools": ["read_file", "list_files"]}
    assert names(only_read, {}) == {"read_file", "list_files"}
    assert names(only_read, {"tools": ["read_file", "write_file"]}) == {"read_file"}
    denied = ModelTools(cfg, only_read, profile={}).execute("write_file", {"path": "/project/x.md", "content": "x"})
    assert "not available" in denied["error"]

    settings["project_access"] = "write"
    settings["tools"], settings["chief_id"] = ["read_file"], "m"
    settings["models"] = [cfg.profile("m", "M", "demo", "simulated", "soul") | {"tools": ["edit_file"]}]
    saved = cfg.save(settings)
    assert saved["tools"] == ["read_file"] and saved["models"][0]["tools"] == ["edit_file"]
    with pytest.raises(ValueError, match="known tool"):
        cfg.save({**settings, "tools": ["run_shell"]})


def test_every_tool_schema_is_valid_for_openai_strict_mode(tmp_path):
    # OpenAI strict function calling rejects optional properties; use a nullable type instead.
    cfg = Config(tmp_path)
    cfg.save_key("BROWSERBASE_API_KEY", "bb-test-key")
    tools = ModelTools(cfg, {**cfg.read(), "project_access": "write"}).definitions
    assert {"write_file", "web_fetch"} <= {t["name"] for t in tools}
    for tool in tools:
        schema = tool["parameters"]
        assert set(schema["required"]) == set(schema["properties"]), tool["name"]
        assert schema["additionalProperties"] is False, tool["name"]


def test_delete_needs_current_hash_and_keeps_a_backup(project, tmp_path):
    root, settings, tools = project
    for args in ({"path": "/project/src/app.py"}, {"path": "/project/src/app.py", "expected_sha256": sha("stale")}):
        with pytest.raises(ProviderError, match="changed since"):
            tools.execute("delete_file", args)
    assert (root / "src/app.py").exists()
    with pytest.raises(ProviderError, match="does not exist"):
        tools.execute("delete_file", {"path": "/project/ghost.md", "expected_sha256": sha("x")})
    with pytest.raises(ProviderError, match="Shared folders|read/write"):
        tools.execute("delete_file", {"path": "/docs/guide.md", "expected_sha256": sha("guide")})
    with pytest.raises(ProviderError, match="read/write"):
        FileTools({**settings, "project_access": "read"}, {}, backup_root=tmp_path / "b").execute(
            "delete_file", {"path": "/project/src/app.py", "expected_sha256": sha("x = 1\ny = 2\n")})
    done = tools.execute("delete_file", {"path": "/project/src/app.py", "expected_sha256": sha("x = 1\ny = 2\n")})
    assert done["deleted"] and not (root / "src/app.py").exists()
    assert [p.read_text() for p in (tmp_path / "backups").rglob("app.py")] == ["x = 1\ny = 2\n"]
