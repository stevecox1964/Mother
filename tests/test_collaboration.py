import json
import threading

import pytest

from mother import providers
from mother.collaboration import knowledge
from test_broadcast import app as app, finished


def result(value):
    return {
        "text": value if isinstance(value, str) else json.dumps(value),
        "usage": {"output_tokens": 12},
    }


def offer(**values):
    return {
        "decision": "offer",
        "relevance": 3,
        "basis": "general",
        "summary": "I can explain this component.",
        "evidence": [],
        **values,
    }


def start(app, **options):
    c = app.test_client()
    cid = c.post("/api/conversations", json={"title": "Knowledge routing"}).json["id"]
    response = c.post(
        f"/api/conversations/{cid}/messages",
        json={
            "content": "Who knows how movement works?",
            "mode": "broadcast",
            **options,
        },
    )
    assert response.status_code == 202, response.json
    return cid, response.json["id"]


def posts(app, cid, kind="contribution"):
    return [e for e in app.extensions["store"].events(cid) if e["kind"] == kind]


def test_context_routes_to_nondefault_and_peers_add_only_deltas(
    app, monkeypatch, tmp_path
):
    (tmp_path / "movement.py").write_text(
        "def move_apc(): return 'local navigation evidence'", encoding="utf-8"
    )
    (tmp_path / "database.py").write_text(
        "DATABASE_ONLY_SOURCE = 'sqlite storage evidence'", encoding="utf-8"
    )
    cfg = app.extensions["mother_config"]
    settings = cfg.read()
    settings.update(
        project_path=str(tmp_path), context_files=["movement.py", "database.py"]
    )
    settings["models"][0].update(
        context_mode="files", context_files=["database.py"], expertise="Storage"
    )
    settings["models"][1].update(
        context_mode="files", context_files=["movement.py"], expertise="Movement"
    )
    settings["models"].append(
        cfg.profile("c", "Unrelated", "demo", "simulated", "Only unrelated topics")
    )
    cfg.save(settings)
    calls = []
    discovery_barrier = threading.Barrier(3, timeout=2)

    def complete(p, system, prompt, *args, **kwargs):
        phase = next(
            x
            for x in ("discovery", "lead", "review", "update")
            if f"MOTHER_PHASE: {x}" in system
        )
        calls.append((p["id"], phase, prompt))
        if phase == "discovery":
            discovery_barrier.wait()
            assert kwargs["tool_runtime"] is None
            assert p["max_tokens"] <= 4096
            if p["id"] == "b":
                assert (
                    "def move_apc()" in prompt and "DATABASE_ONLY_SOURCE" not in prompt
                )
                return result(
                    offer(
                        basis="files",
                        evidence=[
                            {"path": "movement.py", "quote": "def move_apc(): return"}
                        ],
                    )
                )
            assert "def move_apc()" not in prompt
            return result(offer(decision="pass" if p["id"] == "c" else "offer"))
        if phase == "lead":
            assert p["id"] == "b"
            return result("The movement implementation uses local navigation.")
        if phase == "review":
            assert "The movement implementation uses local navigation." in prompt
            assert p["id"] == "a"
            return result(
                {
                    "decision": "contribute",
                    "content": "Storage adds a separate persistence constraint.",
                }
            )
        assert "Storage adds a separate persistence constraint." in prompt
        return result({"decision": "pass", "content": ""})

    monkeypatch.setattr(providers, "complete", complete)
    cid, rid = start(app, rounds=3)
    assert finished(app, rid)["status"] == "completed"
    assert [(p["author"], p["metadata"]["phase"]) for p in posts(app, cid)] == [
        ("Claude voice", "lead"),
        ("OpenAI voice", "review"),
    ]
    assert [phase for mid, phase, _ in calls if mid == "c"] == ["discovery"]
    route = posts(app, cid, "routing")[0]
    assert route["metadata"]["lead_id"] == "b"
    audit = posts(app, cid, "run")
    assert len([e for e in audit if e["metadata"].get("phase") == "discovery"]) == 3
    assert all(e["metadata"]["usage"] for e in audit if e["metadata"].get("phase"))
    snapshot = audit[0]["metadata"]["files"]
    assert [f["path"] for f in snapshot["a"]] == ["database.py"]
    assert [f["path"] for f in snapshot["b"]] == ["movement.py"]
    assert snapshot["c"] == [] and "body" not in snapshot["b"][0]


@pytest.mark.parametrize(
    "review",
    [
        {"decision": "pass", "content": ""},
        {"decision": "contribute", "content": "THE SAME ANSWER!"},
    ],
)
def test_pass_and_duplicate_do_not_publish_or_trigger_update(app, monkeypatch, review):
    phases = []

    def complete(p, system, *args, **kwargs):
        phases.append(system)
        if "MOTHER_PHASE: discovery" in system:
            return result(offer())
        if "MOTHER_PHASE: lead" in system:
            return result("The same answer.")
        return result(review)

    monkeypatch.setattr(providers, "complete", complete)
    cid, rid = start(app, rounds=3)
    assert finished(app, rid)["status"] == "completed"
    assert len(posts(app, cid)) == 1
    assert not any("MOTHER_PHASE: update" in s for s in phases)


def test_reviewers_see_previous_peer_delta(app, monkeypatch):
    cfg = app.extensions["mother_config"]
    settings = cfg.read()
    settings["models"].append(cfg.profile("c", "Third", "demo", "simulated", "Review"))
    cfg.save(settings)

    def complete(p, system, prompt, *args, **kwargs):
        if "MOTHER_PHASE: discovery" in system:
            return result(offer())
        if "MOTHER_PHASE: lead" in system:
            return result("Initial answer")
        if p["id"] == "b":
            return result({"decision": "contribute", "content": "A new shared finding"})
        assert "A new shared finding" in prompt
        return result({"decision": "pass", "content": ""})

    monkeypatch.setattr(providers, "complete", complete)
    cid, rid = start(app)
    assert finished(app, rid)["status"] == "completed"
    assert len(posts(app, cid)) == 2


def test_invalid_or_all_pass_does_not_turn_into_everyone_answering(app, monkeypatch):
    calls = []

    def complete(p, system, *args, **kwargs):
        calls.append(p["id"])
        assert "MOTHER_PHASE: discovery" in system
        return result(
            "I will ignore the schema and echo a whole answer"
            if p["id"] == "a"
            else offer(decision="pass")
        )

    monkeypatch.setattr(providers, "complete", complete)
    cid, rid = start(app)
    assert finished(app, rid)["status"] == "completed_with_errors"
    assert len(calls) == 2 and not posts(app, cid)
    assert any("No available model" in e["content"] for e in posts(app, cid, "system"))
    assert not any(
        "echo a whole answer" in e["content"]
        for e in app.extensions["store"].events(cid)
    )


def test_failed_lead_falls_back_to_next_offer(app, monkeypatch):
    failed_calls = []

    def complete(p, system, *args, **kwargs):
        if "MOTHER_PHASE: discovery" in system:
            return result(offer())
        if p["id"] == "a":
            failed_calls.append(p["id"])
            raise providers.ProviderError("Unavailable")
        return result("Fallback answer")

    monkeypatch.setattr(providers, "complete", complete)
    cid, rid = start(app, rounds=2)
    assert finished(app, rid)["status"] == "completed_with_errors"
    assert [e["author"] for e in posts(app, cid)] == ["Claude voice"]
    assert failed_calls == ["a"]


def test_squelch_discovery_releases_other_speaker_and_discards_late_offer(
    app, monkeypatch
):
    entered, release, done = threading.Event(), threading.Event(), threading.Event()

    def complete(p, system, *args, **kwargs):
        if "MOTHER_PHASE: discovery" in system:
            if p["id"] == "a":
                entered.set()
                release.wait(4)
                done.set()
            return result(offer())
        assert p["id"] == "b"
        return result("Unmuted answer")

    monkeypatch.setattr(providers, "complete", complete)
    cid, rid = start(app)
    try:
        assert entered.wait(2)
        app.test_client().put(
            f"/api/conversations/{cid}/models/a/squelch", json={"squelched": True}
        )
        assert finished(app, rid)["status"] == "completed"
        assert not done.is_set()
        assert [e["author"] for e in posts(app, cid)] == ["Claude voice"]
    finally:
        release.set()
        done.wait(1)


def test_stop_during_discovery_prevents_later_stages(app, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def complete(p, system, *args, **kwargs):
        assert "MOTHER_PHASE: discovery" in system
        entered.set()
        release.wait(4)
        return result(offer())

    monkeypatch.setattr(providers, "complete", complete)
    cid, rid = start(app)
    try:
        assert entered.wait(2)
        response = app.test_client().post(f"/api/runs/{rid}/cancel", json={})
        assert response.status_code == 200
        assert finished(app, rid)["status"] == "cancelled"
        assert not posts(app, cid)
    finally:
        release.set()


def test_evidence_requires_supplied_path_and_matching_quote():
    p = {"expertise": ""}
    candidate = offer(
        basis="files",
        evidence=[{"path": "other.py", "quote": "a fabricated implementation"}],
    )
    assert knowledge(json.dumps(candidate), p, [])["basis"] == "general"
    candidate["evidence"][0]["path"] = "real.py"
    assert not knowledge(
        json.dumps(candidate), p, [{"path": "real.py", "body": "different contents"}]
    )["evidence"]


def test_demo_collaboration_has_one_answer(app):
    cid, rid = start(app)
    assert finished(app, rid)["status"] == "completed"
    assert len(posts(app, cid)) == 1
    assert posts(app, cid)[0]["metadata"]["simulated"]
