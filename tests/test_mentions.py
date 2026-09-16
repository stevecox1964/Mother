import pytest

from mother.mentions import recipient


MODELS = [
    {"id": "a", "name": "Claude", "enabled": True},
    {"id": "b", "name": "Claude Opus 5", "enabled": True},
    {"id": "c", "name": "Disabled", "enabled": False},
]


@pytest.mark.parametrize("text, expected", [
    ("Hello Claude", None), ("Email me@example.com", None),
    ("@Claude hello", "a"), (" @claude opus 5: hello", "b"),
    ('@"Claude Opus 5" hello', "b"), ("@b hello", "b"),
])
def test_recipient(text, expected):
    assert recipient(text, MODELS) == expected


@pytest.mark.parametrize("text", ["@Unknown hello", "@ClaudeX hello", "@Disabled hello", "@Claude"])
def test_invalid_recipient_cannot_broadcast(text):
    with pytest.raises(ValueError):
        recipient(text, MODELS)


def test_duplicate_names_require_id():
    with pytest.raises(ValueError, match="Ambiguous"):
        recipient("@Claude hello", MODELS + [{"id": "d", "name": "Claude", "enabled": True}])


def test_mention_overrides_broadcast_targets_and_squelch_is_respected(tmp_path, monkeypatch):
    from mother.app import create_app
    from mother import providers
    from test_broadcast import finished
    app = create_app(tmp_path / "data")
    c = app.test_client()
    cfg = app.extensions["mother_config"]
    settings = cfg.read()
    settings["models"] = [cfg.profile(m["id"], m["name"], "demo", "simulated", "") for m in MODELS[:2]]
    settings["chief_id"] = "a"
    cfg.save(settings)
    calls = []
    def complete(p, *args, **kwargs):
        calls.append(p["id"])
        return {"text": "single reply", "usage": {}}
    monkeypatch.setattr(providers, "complete", complete)
    cid = c.post("/api/conversations", json={}).json["id"]
    response = c.post(f"/api/conversations/{cid}/messages", json={"content": "@Claude Opus 5 hello", "mode": "broadcast", "targets": ["a"], "rounds": 3})
    assert response.status_code == 202
    run = finished(app, response.json["id"])
    assert run["mode"] == "direct" and calls == ["b"]
    assert [member["model_id"] for member in run["members"]] == ["b"]
    c.put(f"/api/conversations/{cid}/models/b/squelch", json={"squelched": True})
    assert c.post(f"/api/conversations/{cid}/messages", json={"content": "@b hello", "mode": "broadcast"}).status_code == 400
    assert calls == ["b"]
