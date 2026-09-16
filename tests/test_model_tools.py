"""Model discovery, secret boundaries, and native read-only tool continuations."""

import copy
import json
import time
import pytest
from mother.app import create_app
from mother.config import Config
from mother import providers, model_tools
from mother.model_tools import ModelTools, list_models, settings_snapshot


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


@pytest.fixture
def cfg(tmp_path):
    cfg = Config(tmp_path)
    cfg.save_key("TEST_API_KEY", "private-test-credential")
    settings = cfg.read()
    settings["models"] = [
        cfg.profile(p, p.title(), p, "chat-test", "Be concise.")
        for p in ("openai", "anthropic", "gemini", "ollama", "compatible")
    ]
    for p in settings["models"]:
        if p["provider"] != "ollama":
            p["api_key_env"] = "TEST_API_KEY"
        if p["provider"] == "compatible":
            p["base_url"] = "https://example.test/v1"
    settings["chief_id"] = "openai"
    cfg.save(settings)
    return cfg


@pytest.mark.parametrize(
    "provider,body,expected,header",
    [
        ("openai", {"data": [{"id": "new-chat"}]}, "new-chat", "Authorization"),
        (
            "anthropic",
            {
                "data": [{"id": "claude-new", "display_name": "Claude New"}],
                "has_more": False,
            },
            "claude-new",
            "x-api-key",
        ),
        (
            "gemini",
            {
                "models": [
                    {
                        "name": "models/gemini-new",
                        "displayName": "Gemini New",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ]
            },
            "gemini-new",
            "x-goog-api-key",
        ),
        ("ollama", {"models": [{"name": "local:latest"}]}, "local:latest", None),
        ("compatible", {"data": [{"id": "proxy-chat"}]}, "proxy-chat", "Authorization"),
    ],
)
def test_catalog_provider_endpoints_and_auth(
    cfg, monkeypatch, provider, body, expected, header
):
    requests = []

    def get(url, **kwargs):
        requests.append((url, kwargs))
        return Response(body)

    monkeypatch.setattr(model_tools.requests, "get", get)
    result = list_models(cfg, provider)
    assert result["models"][0]["id"] == expected
    assert "private-test-credential" not in json.dumps(result)
    url, kwargs = requests[0]
    assert url.endswith("/api/tags" if provider == "ollama" else "/models")
    assert kwargs["allow_redirects"] is False
    assert (
        "json" not in kwargs
    )  # Catalog requests contain no conversation or instructions.
    if header:
        assert "private-test-credential" in kwargs["headers"][header]
    else:
        assert kwargs["headers"] == {}


@pytest.mark.parametrize(
    "provider,cursor_key,body_key",
    [("anthropic", "after_id", "data"), ("gemini", "pageToken", "models")],
)
def test_catalog_pagination_and_deduplication(
    cfg, monkeypatch, provider, cursor_key, body_key
):
    seen = []

    def get(url, **kwargs):
        seen.append(copy.deepcopy(kwargs["params"]))
        more = len(seen) == 1
        rows = [{"id": "first"}, {"id": "second"}] if not more else [{"id": "first"}]
        if provider == "gemini":
            return Response(
                {
                    body_key: [{"name": "models/" + r["id"]} for r in rows],
                    **({"nextPageToken": "next"} if more else {}),
                }
            )
        return Response({body_key: rows, "has_more": more, "last_id": "next"})

    monkeypatch.setattr(model_tools.requests, "get", get)
    result = list_models(cfg, provider)
    assert [m["id"] for m in result["models"]] == ["first", "second"]
    assert seen[1][cursor_key] == "next"
    assert not result["truncated"]


@pytest.mark.parametrize(
    "body",
    [{"data": None}, {"data": [{}]}, {"data": [1]}, [], {"data": [], "has_more": True}],
)
def test_catalog_rejects_malformed_response(cfg, monkeypatch, body):
    monkeypatch.setattr(model_tools.requests, "get", lambda *a, **kw: Response(body))
    with pytest.raises(providers.ProviderError, match="invalid model list"):
        list_models(cfg, "openai")


def test_failed_catalog_never_echoes_upstream_or_follows_redirect(cfg, monkeypatch):
    monkeypatch.setattr(
        model_tools.requests,
        "get",
        lambda *a, **kw: Response({"error": "private-test-credential"}, 302),
    )
    with pytest.raises(providers.ProviderError) as exc:
        list_models(cfg, "openai")
    assert "302" in str(exc.value) and "private-test-credential" not in str(exc.value)


def test_settings_are_snapshot_allowlist_with_secret_redaction(cfg, monkeypatch):
    settings = cfg.read()
    settings["models"][0]["soul"] = "Never expose private-test-credential"
    settings["models"][0]["unexpected"] = "private-test-credential"
    runtime = ModelTools(cfg, settings)
    settings["models"][0]["model"] = "changed-after-message"
    result = runtime.execute("get_model_settings", {"profile_id": "openai"})
    assert result["models"][0]["model"] == "chat-test"
    assert "private-test-credential" not in json.dumps(result)
    assert "[redacted]" in result["models"][0]["instructions"]
    assert (
        "api_key_env" not in result["models"][0]
        and "unexpected" not in result["models"][0]
    )
    assert "instructions" not in settings_snapshot(cfg, settings)["models"][0]
    assert "error" in runtime.execute("change_model_settings", {})
    assert "error" in runtime.execute(
        "list_provider_models", {"provider": "openai", "url": "https://arbitrary.test"}
    )
    assert "error" in runtime.execute("get_model_settings", "invalid json")


def test_catalog_memoized_and_connection_choice_explicit(cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(
        model_tools.requests,
        "get",
        lambda *a, **kw: calls.append(1) or Response({"data": [{"id": "live"}]}),
    )
    runtime = ModelTools(cfg, cfg.read())
    for _ in range(2):
        assert (
            runtime.execute("list_provider_models", {"provider": "openai"})["models"][
                0
            ]["id"]
            == "live"
        )
    assert len(calls) == 1
    settings = cfg.read()
    extra = dict(settings["models"][0], id="second", base_url="https://second.test/v1")
    settings["models"].append(extra)
    with pytest.raises(providers.ProviderError, match="multiple saved connections"):
        list_models(cfg, "openai", settings=settings)
    with pytest.raises(providers.ProviderError, match="does not belong"):
        list_models(cfg, "anthropic", "openai")
    cfg.save_key("TEST_API_KEY", "")
    monkeypatch.delenv("TEST_API_KEY", raising=False)
    with pytest.raises(providers.ProviderError, match="No credential"):
        list_models(cfg, "openai")
    assert len(calls) == 1


def tool_response(provider, n=1):
    args = {"profile_id": None}
    if provider == "openai":
        return {
            "output": [
                {
                    "type": "reasoning",
                    "id": "reasoning-id",
                    "encrypted_content": "opaque-reasoning",
                    "summary": [],
                }
            ]
            + [
                dict(
                    type="function_call",
                    name="get_model_settings",
                    arguments=json.dumps(args),
                    call_id=f"c{i}",
                )
                for i in range(n)
            ],
            "usage": {"input_tokens": 10},
        }
    if provider == "anthropic":
        return {
            "content": [
                dict(type="tool_use", id=f"c{i}", name="get_model_settings", input=args)
                for i in range(n)
            ],
            "usage": {"input_tokens": 10},
        }
    if provider == "gemini":
        return {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_model_settings",
                                    "args": args,
                                    "id": f"c{i}",
                                },
                                "thoughtSignature": "opaque-signature",
                            }
                            for i in range(n)
                        ],
                    }
                }
            ],
            "usageMetadata": {"promptTokenCount": 10},
        }
    msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": f"c{i}",
                "type": "function",
                "function": {
                    "name": "get_model_settings",
                    "arguments": args if provider == "ollama" else json.dumps(args),
                },
            }
            for i in range(n)
        ],
    }
    return (
        {"message": msg, "prompt_eval_count": 10}
        if provider == "ollama"
        else {"choices": [{"message": msg}], "usage": {"input_tokens": 10}}
    )


def final_response(provider):
    if provider == "openai":
        return {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Final answer."}],
                }
            ],
            "usage": {"input_tokens": 5},
        }
    if provider == "anthropic":
        return {
            "content": [{"type": "text", "text": "Final answer."}],
            "usage": {"input_tokens": 5},
        }
    if provider == "gemini":
        return {
            "candidates": [{"content": {"parts": [{"text": "Final answer."}]}}],
            "usageMetadata": {"promptTokenCount": 5},
        }
    msg = {"role": "assistant", "content": "Final answer."}
    return (
        {"message": msg, "prompt_eval_count": 5}
        if provider == "ollama"
        else {"choices": [{"message": msg}], "usage": {"input_tokens": 5}}
    )


@pytest.mark.parametrize(
    "provider", ["openai", "anthropic", "gemini", "ollama", "compatible"]
)
def test_native_roundtrip_preserves_continuations_and_usage(cfg, monkeypatch, provider):
    sent = []

    def post(url, **kwargs):
        sent.append(copy.deepcopy(kwargs["json"]))
        return Response(
            tool_response(provider) if len(sent) == 1 else final_response(provider)
        )

    monkeypatch.setattr(providers.requests, "post", post)
    runtime = ModelTools(cfg, cfg.read())
    p = next(p for p in cfg.read()["models"] if p["provider"] == provider)
    result = providers.complete(p, "system", "prompt", cfg.key(p), tool_runtime=runtime)
    assert result["text"] == "Final answer." and result["provider_requests"] == 2
    assert 15 in result["usage"].values()
    assert len(runtime.audit) == 1
    assert "tools" in sent[0]
    assert "private-test-credential" not in json.dumps(sent)
    serialized = json.dumps(sent[1])
    assert "default_model_id" in serialized
    if provider == "openai":
        assert "opaque-reasoning" in serialized and sent[0]["include"] == [
            "reasoning.encrypted_content"
        ]
        assert sent[1]["input"][-1]["call_id"] == "c0"
    elif provider == "anthropic":
        assert sent[1]["messages"][-1]["content"][0]["tool_use_id"] == "c0"
    elif provider == "gemini":
        assert (
            "opaque-signature" in serialized
            and sent[1]["contents"][-1]["parts"][0]["functionResponse"]["id"] == "c0"
        )
        assert sent[0]["tools"][0]["functionDeclarations"][0]["parameters"][
            "properties"
        ]["profile_id"]["nullable"]
    elif provider == "compatible":
        assert sent[1]["messages"][-1]["tool_call_id"] == "c0"
    else:
        assert sent[1]["messages"][-1]["tool_name"] == "get_model_settings"


def test_tool_budget_and_cancellation_prevent_unbounded_calls(cfg, monkeypatch):
    posts = []
    monkeypatch.setattr(
        providers.requests,
        "post",
        lambda *a, **kw: (
            posts.append(copy.deepcopy(kw["json"]))
            or Response(tool_response("openai", 10))
        ),
    )
    runtime = ModelTools(cfg, cfg.read())
    p = cfg.read()["models"][0]
    with pytest.raises(providers.ProviderError, match="tool limit"):
        providers.complete(p, "system", "prompt", cfg.key(p), tool_runtime=runtime)
    assert len(posts) == providers.MAX_REQUESTS and len(runtime.audit) == providers.MAX_TOOL_CALLS
    # Ten calls per response reach the call budget after four requests; tools are then withdrawn.
    assert "tool_choice" not in posts[3] and posts[4]["tool_choice"] == "none"
    posts.clear()
    runtime = ModelTools(cfg, cfg.read())
    with pytest.raises(providers.ProviderError, match="Reply stopped"):
        providers.complete(
            p,
            "system",
            "prompt",
            cfg.key(p),
            tool_runtime=runtime,
            alive=lambda: not posts,
        )
    assert len(posts) == 1 and not runtime.audit


def test_chat_tools_yield_one_visible_reply_and_settings(cfg, monkeypatch):
    app = create_app(cfg.root)
    app.config["TESTING"] = True
    client = app.test_client()
    sent = []

    def post(url, **kwargs):
        sent.append(copy.deepcopy(kwargs["json"]))
        return Response(
            tool_response("openai") if len(sent) == 1 else final_response("openai")
        )

    monkeypatch.setattr(providers.requests, "post", post)
    cid = client.post("/api/conversations", json={}).json["id"]
    run = client.post(
        f"/api/conversations/{cid}/messages",
        json={"content": "What are my model settings?"},
    ).json
    store = app.extensions["store"]
    deadline = time.monotonic() + 5
    while store.run(run["id"])["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.02)
    assert store.run(run["id"])["status"] == "completed"
    events = store.events(cid)
    assert [e["kind"] for e in events] == ["user", "run", "reply"]
    assert events[-1]["content"] == "Final answer."
    assert events[-1]["metadata"]["provider_requests"] == 2
    assert len(events[-1]["metadata"]["tools"]) == 1
    assert (
        "Mother model settings at message start"
        in sent[0]["input"][0]["content"][0]["text"]
    )
    assert "private-test-credential" not in json.dumps(sent)


def test_catalog_api_and_tools_disabled_persist(cfg, monkeypatch):
    app = create_app(cfg.root)
    c = app.test_client()
    monkeypatch.setattr(
        model_tools.requests,
        "get",
        lambda *a, **kw: Response({"data": [{"id": "fresh-id"}]}),
    )
    response = c.get("/api/providers/openai/models?profile_id=openai")
    assert (
        response.status_code == 200 and response.json["models"][0]["id"] == "fresh-id"
    )
    assert c.get("/api/providers/openai/models?profile_id=anthropic").status_code == 502
    assert (
        c.get(
            "/api/providers/openai/models", headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    settings = cfg.read()
    settings["models"][0]["tools_enabled"] = False
    assert c.put("/api/settings", json=settings).status_code == 200
    assert Config(cfg.root).read()["models"][0]["tools_enabled"] is False


def test_ordinary_chat_with_tools_still_uses_one_request(cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(
        providers.requests,
        "post",
        lambda *a, **kw: (
            sent.append(copy.deepcopy(kw["json"])) or Response(final_response("openai"))
        ),
    )
    p = cfg.read()["models"][0]
    runtime = ModelTools(cfg, cfg.read())
    result = providers.complete(p, "system", "Hello", cfg.key(p), tool_runtime=runtime)
    assert result["provider_requests"] == 1 and len(sent) == 1 and not runtime.audit


def test_repeated_pagination_cursor_is_rejected(cfg, monkeypatch):
    seen = []
    monkeypatch.setattr(
        model_tools.requests,
        "get",
        lambda *a, **kw: (
            seen.append(1)
            or Response({"data": [{"id": "same"}], "has_more": True, "last_id": "same"})
        ),
    )
    with pytest.raises(providers.ProviderError, match="invalid model list"):
        list_models(cfg, "anthropic")
    assert len(seen) == 2


def test_disabled_tools_keep_settings_visible_in_chat(cfg, monkeypatch):
    settings = cfg.read()
    settings["models"][0]["tools_enabled"] = False
    cfg.save(settings)
    app = create_app(cfg.root)
    c = app.test_client()
    sent = []
    monkeypatch.setattr(
        providers.requests,
        "post",
        lambda *a, **kw: (
            sent.append(copy.deepcopy(kw["json"])) or Response(final_response("openai"))
        ),
    )
    cid = c.post("/api/conversations", json={}).json["id"]
    run = c.post(
        f"/api/conversations/{cid}/messages", json={"content": "What model am I using?"}
    ).json
    store = app.extensions["store"]
    deadline = time.monotonic() + 5
    while store.run(run["id"])["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.02)
    assert store.run(run["id"])["status"] == "completed"
    assert len(sent) == 1 and "tools" not in sent[0]
    assert (
        "Mother model settings at message start"
        in sent[0]["input"][0]["content"][0]["text"]
    )
