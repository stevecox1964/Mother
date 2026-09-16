import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from mother.app import create_app
from mother.store import Store
from mother import providers


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path / "data")
    cfg = app.extensions["mother_config"]
    settings = cfg.read()
    settings["models"] = [
        cfg.profile("a", "OpenAI voice", "demo", "simulated", "Be precise."),
        cfg.profile("b", "Claude voice", "demo", "simulated", "Challenge assumptions."),
    ]
    settings["chief_id"] = "a"
    cfg.save(settings)
    return app


def start(app, **options):
    c = app.test_client()
    cid = c.post("/api/conversations", json={"title": "Shared project"}).json["id"]
    r = c.post(
        f"/api/conversations/{cid}/messages",
        json={"content": "Design the shared project", "mode": "opinions", **options},
    )
    assert r.status_code == 202, r.json
    return cid, r.json["id"]


def finished(app, rid):
    store = app.extensions["store"]
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        row = store.run(rid)
        if row["status"] != "running":
            return row
        time.sleep(0.02)
    raise AssertionError("Discussion did not finish")


def test_concurrent_broadcast_and_peer_discussion(app, monkeypatch):
    barrier = threading.Barrier(2, timeout=2)
    calls = []

    def complete(p, system, prompt, *args, **kwargs):
        barrier.wait()
        calls.append((p["id"], system, prompt))
        return {"text": p["id"] + "_EVIDENCE", "usage": {}}

    monkeypatch.setattr(providers, "complete", complete)
    cid, rid = start(app)
    assert finished(app, rid)["status"] == "completed"
    events = app.extensions["store"].events(cid)
    posts = [e for e in events if e["kind"] == "contribution"]
    assert len(posts) == 4
    assert [p["metadata"]["round"] for p in posts] == [1, 1, 2, 2]
    assert {p["author"] for p in posts} == {"OpenAI voice", "Claude voice"}
    assert not any(e["kind"] == "synthesis" for e in events)
    for mid, system, prompt in calls:
        assert "No model is chief" in system
        if "Round 1:" in system:
            assert "a_EVIDENCE" not in prompt and "b_EVIDENCE" not in prompt
        else:
            assert "a_EVIDENCE" in prompt and "b_EVIDENCE" in prompt
    assert {p["status"] for p in app.extensions["store"].runs(cid)[0]["members"]} == {
        "replied"
    }


def test_selected_subset_and_direct_remain_independent(app):
    cid, rid = start(app, targets=["b"], rounds=1)
    finished(app, rid)
    assert [
        e["author"]
        for e in app.extensions["store"].events(cid)
        if e["kind"] == "contribution"
    ] == ["Claude voice"]
    c = app.test_client()
    r = c.post(
        f"/api/conversations/{cid}/messages",
        json={
            "content": "Now only you",
            "mode": "direct",
            "targets": ["a"],
            "rounds": 3,
        },
    )
    finished(app, r.json["id"])
    posts = [e for e in app.extensions["store"].events(cid) if e["kind"] == "reply"]
    assert len(posts) == 1 and posts[0]["author"] == "OpenAI voice"


def test_squelch_drops_inflight_without_holding_peers(app, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    late_done = threading.Event()
    calls = []

    def complete(p, *args, **kwargs):
        calls.append(p["id"])
        if p["id"] == "b":
            entered.set()
            release.wait(5)
            late_done.set()
            return {"text": "MUST_NOT_APPEAR", "usage": {}}
        return {"text": "Peer keeps discussing", "usage": {}}

    monkeypatch.setattr(providers, "complete", complete)
    cid, rid = start(app)
    try:
        assert entered.wait(2)
        c = app.test_client()
        result = c.put(
            f"/api/conversations/{cid}/models/b/squelch", json={"squelched": True}
        )
        assert result.status_code == 200
        assert finished(app, rid)["status"] == "completed"
        # The unsquelched model completes round two while the muted HTTP call is still blocked.
        assert (
            not late_done.is_set() and calls.count("a") == 2 and calls.count("b") == 1
        )
        release.set()
        assert late_done.wait(1)
        time.sleep(0.05)
        assert not any(
            "MUST_NOT_APPEAR" in e["content"]
            for e in app.extensions["store"].events(cid)
        )
        assert app.extensions["store"].voice(cid, "b")["squelched"]
    finally:
        release.set()


def test_squelch_revision_survives_unmute_and_restart(app):
    s = app.extensions["store"]
    cid = s.create_conversation("Project")["id"]
    run = s.start_run(cid, "broadcast", 2, ["a", "b"])
    assert s.can_speak(run["id"], "b", 0)
    s.set_squelch(cid, "b", True)
    s.set_squelch(cid, "b", False)
    assert not s.can_speak(run["id"], "b", 0)
    assert not s.publish_reply(
        run, "b", 0, "contribution", "Claude", "Old response", {}
    )
    assert s.can_speak(run["id"], "b", 2)
    s.set_squelch(cid, "b", True)
    s.finish(run["id"], "completed")
    reopened = Store(s.root)
    assert reopened.voice(cid, "b")["squelched"]
    assert reopened.voice(cid, "b")["revision"] == 3
    assert (
        reopened.voice(reopened.create_conversation("Other project")["id"], "b")[
            "squelched"
        ]
        == 0
    )


def test_all_squelched_ends_run_and_blocks_new_calls(app, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def complete(*args, **kwargs):
        entered.set()
        release.wait(4)
        return {"text": "Late", "usage": {}}

    monkeypatch.setattr(providers, "complete", complete)
    cid, rid = start(app)
    try:
        assert entered.wait(2)
        c = app.test_client()
        for mid in ("a", "b"):
            c.put(
                f"/api/conversations/{cid}/models/{mid}/squelch",
                json={"squelched": True},
            )
        assert finished(app, rid)["status"] == "squelched"
        r = c.post(
            f"/api/conversations/{cid}/messages",
            json={"content": "Again", "mode": "broadcast"},
        )
        assert r.status_code == 400 and "squelched" in r.json["error"]
        c.put(f"/api/conversations/{cid}/models/a/squelch", json={"squelched": False})
        assert app.extensions["store"].run(rid)["status"] == "squelched"
    finally:
        release.set()


def test_squelch_and_publish_are_serialized(app):
    s = app.extensions["store"]
    cid = s.create_conversation("Race")["id"]
    for _ in range(8):
        s.set_squelch(cid, "b", False)
        rev = s.voice(cid, "b")["revision"]
        run = s.start_run(cid, "broadcast", 1, ["a", "b"])
        with ThreadPoolExecutor(2) as pool:
            mute = pool.submit(s.set_squelch, cid, "b", True)
            post = pool.submit(
                s.publish_reply,
                run,
                "b",
                rev,
                "contribution",
                "Claude",
                "RACING_REPLY",
                {"run_id": run["id"]},
            )
            mute.result()
            post.result()
        events = s.events(cid)
        muted = max(e["seq"] for e in events if e["metadata"].get("squelched") is True)
        assert not any(
            e["seq"] > muted and e["metadata"].get("run_id") == run["id"]
            for e in events
        )
        s.finish(run["id"], "completed")


def test_failed_voice_does_not_stop_others(app, monkeypatch):
    def complete(p, *args, **kwargs):
        if p["id"] == "b":
            raise providers.ProviderError("Provider quota reached")
        return {"text": "A useful contribution", "usage": {}}

    monkeypatch.setattr(providers, "complete", complete)
    cid, rid = start(app)
    assert finished(app, rid)["status"] == "completed_with_errors"
    posts = app.extensions["store"].events(cid)
    assert len([e for e in posts if e["kind"] == "contribution"]) == 2
    assert len([e for e in posts if e["kind"] == "error"]) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "unknown"},
        {"rounds": 0},
        {"rounds": 4},
        {"rounds": True},
        {"targets": ["missing"]},
    ],
)
def test_invalid_broadcast_rejected(app, payload):
    c = app.test_client()
    cid = c.post("/api/conversations", json={}).json["id"]
    r = c.post(
        f"/api/conversations/{cid}/messages",
        json={"content": "Hello", "mode": "broadcast", **payload},
    )
    assert r.status_code == 400 and app.extensions["store"].events(cid) == []
