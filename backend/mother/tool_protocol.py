"""Translate the same read-only tools into each provider's native wire format."""

import copy
import json


def attach(payload, provider, definitions):
    definitions = copy.deepcopy(definitions)
    if provider == "openai":
        payload["tools"] = [
            dict(type="function", strict=True, **d) for d in definitions
        ]
        # Stateless Responses continuations must carry reasoning along with tool calls.
        payload["include"] = ["reasoning.encrypted_content"]
    elif provider == "anthropic":
        payload["tools"] = [
            dict(
                name=d["name"],
                description=d["description"],
                input_schema=d["parameters"],
            )
            for d in definitions
        ]
    elif provider == "gemini":
        for d in definitions:
            schema = d["parameters"]
            schema.pop("additionalProperties", None)
            for prop in schema["properties"].values():
                if isinstance(prop["type"], list):
                    prop["type"], prop["nullable"] = "string", True
        payload["tools"] = [{"functionDeclarations": definitions}]
    else:
        payload["tools"] = [dict(type="function", function=d) for d in definitions]


def calls_from(body, provider):
    if provider == "openai":
        return [
            (c["name"], c.get("arguments", {}), c["call_id"])
            for c in body.get("output", [])
            if c.get("type") == "function_call"
        ]
    if provider == "anthropic":
        return [
            (c["name"], c.get("input", {}), c["id"])
            for c in body.get("content", [])
            if c.get("type") == "tool_use"
        ]
    if provider == "gemini":
        parts = (body.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        return [
            (
                p["functionCall"]["name"],
                p["functionCall"].get("args", {}),
                p["functionCall"].get("id"),
            )
            for p in parts
            if "functionCall" in p
        ]
    message = (
        body.get("message", {})
        if provider == "ollama"
        else body["choices"][0]["message"]
    )
    return [
        (c["function"]["name"], c["function"].get("arguments", {}), c.get("id"))
        for c in message.get("tool_calls", [])
    ]


def continue_with_results(payload, provider, body, calls, results):
    if provider == "openai":
        payload["input"].extend(body["output"])
        payload["input"].extend(
            {
                "type": "function_call_output",
                "call_id": call[2],
                "output": json.dumps(result),
            }
            for call, result in zip(calls, results)
        )
    elif provider == "anthropic":
        payload["messages"].append({"role": "assistant", "content": body["content"]})
        payload["messages"].append(
            {
                "role": "user",
                "content": [
                    dict(
                        type="tool_result",
                        tool_use_id=call[2],
                        content=json.dumps(result),
                        is_error="error" in result,
                    )
                    for call, result in zip(calls, results)
                ],
            }
        )
    elif provider == "gemini":
        # Preserve thought signatures and every original part verbatim.
        payload["contents"].append(body["candidates"][0]["content"])
        parts = []
        for call, result in zip(calls, results):
            response = dict(name=call[0], response=result)
            if call[2]:
                response["id"] = call[2]
            parts.append({"functionResponse": response})
        payload["contents"].append({"role": "user", "parts": parts})
    else:
        message = (
            body["message"] if provider == "ollama" else body["choices"][0]["message"]
        )
        payload["messages"].append(message)
        for call, result in zip(calls, results):
            tool_message = dict(role="tool", content=json.dumps(result))
            tool_message["tool_name" if provider == "ollama" else "tool_call_id"] = (
                call[0] if provider == "ollama" else call[2]
            )
            payload["messages"].append(tool_message)


def finish_without_tools(payload, provider):
    if provider == "gemini":
        payload["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
    elif provider == "ollama":
        payload.pop("tools", None)
    else:
        payload["tool_choice"] = {"type": "none"} if provider == "anthropic" else "none"


def usage_from(body, provider):
    if provider == "gemini":
        return body.get("usageMetadata") or {}
    if provider == "ollama":
        return {k: body[k] for k in ("prompt_eval_count", "eval_count") if k in body}
    return body.get("usage") or {}


def add_usage(total, usage):
    for key, value in usage.items():
        if isinstance(value, dict):
            add_usage(total.setdefault(key, {}), value)
        elif isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + value
