"""HTTP adapters adapted from Unreal llm_router/ollama_adapter and BMM query()."""

import re
import json
from urllib.parse import quote
import requests
from . import tool_protocol


class ProviderError(RuntimeError):
    pass


# Tool budget per completion: enough for read, edit, re-read work, still bounded.
MAX_REQUESTS = 12
MAX_TOOL_CALLS = 40


def complete(
    profile,
    system,
    prompt,
    key="",
    images=None,
    *,
    tool_runtime=None,
    alive=lambda: True,
):
    provider = profile["provider"]
    images = images or []
    if provider == "demo":
        if "MOTHER_PHASE: discovery" in system:
            return {
                "text": json.dumps(
                    {
                        "decision": "offer",
                        "relevance": 1,
                        "basis": "general",
                        "summary": "Simulated participant for demonstrating speaker selection.",
                        "evidence": [],
                    }
                ),
                "usage": {},
                "simulated": True,
            }
        if "MOTHER_PHASE: review" in system or "MOTHER_PHASE: update" in system:
            return {
                "text": json.dumps({"decision": "pass", "content": ""}),
                "usage": {},
                "simulated": True,
            }
        return {
            "text": f"### {profile['name']} · simulated response\nI received the conversation, my configured soul, and {'selected project files' if '--- FILE:' in prompt else 'board context'}.\n\nIn a live chat I would answer your message using the conversation and any selected project files.\n\nNo model API was called.",
            "usage": {},
            "simulated": True,
        }
    if provider not in ("ollama", "compatible") and not key:
        raise ProviderError(
            f"Missing {profile['api_key_env']}. Add the credential in settings."
        )
    base = profile["base_url"]
    model = profile["model"]
    cap = profile["max_tokens"]
    headers = {"Content-Type": "application/json"}
    if provider == "openai":
        content = [{"type": "input_text", "text": prompt}] + [
            {"type": "input_image", "image_url": im["data_url"]} for im in images
        ]
        endpoint = base + "/responses"
        headers["Authorization"] = "Bearer " + key
        payload = {
            "model": model,
            "instructions": system,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": cap,
            "store": False,
        }
    elif provider == "anthropic":
        content = [{"type": "text", "text": prompt}] + [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": im["mime"],
                    "data": im["base64"],
                },
            }
            for im in images
        ]
        endpoint = base + "/messages"
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
        payload = {
            "model": model,
            "system": system,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": cap,
        }
    elif provider == "gemini":
        endpoint = (
            base
            + "/models/"
            + quote(model.removeprefix("models/"), safe="")
            + ":generateContent"
        )
        headers["x-goog-api-key"] = key
        parts = [{"text": prompt}] + [
            {"inlineData": {"mimeType": im["mime"], "data": im["base64"]}}
            for im in images
        ]
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"maxOutputTokens": cap},
        }
    elif provider == "ollama":
        endpoint = base + "/api/chat"
        msg = {"role": "user", "content": prompt}
        if images:
            msg["images"] = [im["base64"] for im in images]
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, msg],
            "stream": False,
            "think": False,
            "keep_alive": "5m",
            "options": {"num_predict": cap},
        }
    elif provider == "compatible":
        endpoint = base + "/chat/completions"
        if key:
            headers["Authorization"] = "Bearer " + key
        content = [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": im["data_url"]}} for im in images
        ]
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content if images else prompt},
            ],
            "max_tokens": cap,
        }
    else:
        raise ProviderError("Unknown provider.")
    if tool_runtime:
        tool_protocol.attach(payload, provider, tool_runtime.definitions)
    total_usage, tool_count = {}, 0
    try:
        for request_index in range(MAX_REQUESTS):
            if not alive():
                raise ProviderError("Reply stopped.")
            body = _post(endpoint, payload, headers)
            tool_protocol.add_usage(
                total_usage, tool_protocol.usage_from(body, provider)
            )
            calls = tool_protocol.calls_from(body, provider) if tool_runtime else []
            if not calls:
                break
            if request_index == MAX_REQUESTS - 1 or len(calls) > 32:
                raise ProviderError(
                    "Model exceeded the tool limit. Try a narrower model question."
                )
            results = []
            for name, arguments, call_id in calls:
                if not alive():
                    raise ProviderError("Reply stopped.")
                result = (
                    tool_runtime.execute(name, arguments)
                    if tool_count < MAX_TOOL_CALLS
                    else {
                        "error": "Tool limit reached. Answer using the results already provided."
                    }
                )
                results.append(result)
                tool_count += 1
            tool_protocol.continue_with_results(payload, provider, body, calls, results)
            if request_index == MAX_REQUESTS - 2 or tool_count >= MAX_TOOL_CALLS:
                tool_protocol.finish_without_tools(payload, provider)
        if provider == "openai":
            text = "".join(
                c.get("text", "")
                for item in body.get("output", [])
                for c in item.get("content", [])
                if c.get("type") == "output_text"
            )
            truncated = body.get("status") == "incomplete"
        elif provider == "anthropic":
            text = "".join(
                c.get("text", "")
                for c in body.get("content", [])
                if c.get("type") == "text"
            )
            truncated = body.get("stop_reason") == "max_tokens"
        elif provider == "gemini":
            candidate = (body.get("candidates") or [{}])[0]
            text = "".join(
                p.get("text", "")
                for p in candidate.get("content", {}).get("parts", [])
                if not p.get("thought")
            )
            truncated = candidate.get("finishReason") == "MAX_TOKENS"
        elif provider == "ollama":
            text = re.sub(
                r"<think>.*?</think>",
                "",
                body.get("message", {}).get("content", ""),
                flags=re.DOTALL | re.IGNORECASE,
            )
            truncated = body.get("done_reason") == "length"
        else:
            choice = body["choices"][0]
            text = choice["message"].get("content", "")
            truncated = choice.get("finish_reason") == "length"
        if not isinstance(text, str) or not text.strip():
            raise ProviderError(
                "Provider returned no text. It may need a larger output budget or different model settings."
            )
        return {
            "text": text.strip(),
            "usage": total_usage,
            "provider_requests": request_index + 1,
            "truncated": truncated,
            "simulated": False,
        }
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise ProviderError(
            "Provider returned an unexpected response format."
        ) from None


def _post(endpoint, payload, headers):
    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=(10, 120),
            allow_redirects=False,
        )
    except requests.RequestException:
        raise ProviderError(
            "Provider connection failed or timed out. Check the endpoint and local server."
        ) from None
    if response.status_code >= 300:
        # Do not echo upstream bodies: they can contain keys, prompts or proxy credentials.
        hints = {
            400: "Request rejected: check model ID, token limit, image support and tool support. Disable model tools in settings if unsupported.",
            401: "Credential rejected.",
            403: "Access denied for this model.",
            404: "Model or endpoint not found.",
            429: "Rate limit or provider quota reached.",
        }
        raise ProviderError(
            f"Provider HTTP {response.status_code}. {hints.get(response.status_code, 'Provider request failed.')}"
        )
    try:
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError()
        return body
    except (ValueError, TypeError):
        raise ProviderError(
            "Provider returned an unexpected response format."
        ) from None
