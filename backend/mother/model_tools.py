"""Read-only model configuration and provider model catalogs."""

from datetime import datetime, timezone
from pathlib import Path
import copy
import json
import time

import requests
from .config import PROVIDERS
from .providers import ProviderError
from .file_tools import FileTools, FILE_TOOL_DEFINITIONS, WRITE_TOOLS
from .web_tools import WebTools, WEB_TOOL_DEFINITIONS, KEY_NAME as WEB_KEY_NAME

MODEL_TOOL_DEFINITIONS = [
    {
        "name": "get_model_settings",
        "description": "Read Mother's configured model profiles, default model, enabled flags, token limits, image/context access, and instructions. Credentials are never returned. Use this for questions about current model settings.",
        "parameters": {
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": ["string", "null"],
                    "description": "A configured profile ID, or null for all profiles.",
                }
            },
            "required": ["profile_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_provider_models",
        "description": "Fetch model IDs and names from a provider's models API using Mother's saved connection and credentials. Use for current model names instead of guessing. Supports OpenAI, Anthropic, Gemini, installed Ollama models, and configured OpenAI-compatible endpoints. Read-only; does not enable, download, or change a model.",
        "parameters": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "enum": list(PROVIDERS)},
                "profile_id": {
                    "type": ["string", "null"],
                    "description": "Saved profile whose endpoint/credential to use, or null to select the provider's configured connection.",
                },
            },
            "required": ["provider", "profile_id"],
            "additionalProperties": False,
        },
    },
]


def redact(value, secrets):
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[redacted]")
        return value
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, dict):
        return {k: redact(v, secrets) for k, v in value.items()}
    return value


def settings_snapshot(config, settings, include_instructions=False):
    keys = {config.key(p) for p in settings["models"]}
    result = {"default_model_id": settings["chief_id"], "models": []}
    for p in settings["models"]:
        row = {
            k: p[k]
            for k in (
                "id",
                "name",
                "provider",
                "model",
                "enabled",
                "base_url",
                "max_tokens",
                "vision",
                "context_mode",
            )
        }
        row["credential_configured"] = bool(config.key(p))
        row["tools_enabled"] = p.get("tools_enabled", True)
        row["expertise"] = p.get("expertise", "")
        row["assigned_files"] = p.get("context_files")
        if include_instructions:
            row["instructions"] = p["soul"][:2000]
            row["instructions_truncated"] = len(p["soul"]) > 2000
        result["models"].append(row)
    return redact(result, keys)


def list_models(config, provider, profile_id=None, settings=None, alive=lambda: True):
    if provider not in PROVIDERS:
        raise ProviderError(
            "Unknown provider. Choose OpenAI, Anthropic, Gemini, Ollama, or a configured compatible endpoint."
        )
    settings = settings if settings is not None else config.read()
    profiles = [p for p in settings["models"] if p["provider"] == provider]
    if profile_id:
        profile = next((p for p in profiles if p["id"] == profile_id), None)
        if profile is None:
            raise ProviderError(
                "The requested profile does not belong to this provider. Save its connection settings first."
            )
    else:
        connections = {(p["base_url"], p["api_key_env"]) for p in profiles}
        if len(connections) > 1:
            raise ProviderError(
                "This provider has multiple saved connections. Specify a profile_id from get_model_settings."
            )
        profile = (
            profiles[0]
            if profiles
            else {
                "base_url": PROVIDERS[provider][1],
                "api_key_env": PROVIDERS[provider][2],
            }
        )
    if provider == "demo":
        return dict(
            provider=provider,
            models=[{"id": "simulated", "name": "Simulated demo"}],
            fetched_at=datetime.now(timezone.utc).isoformat(),
            truncated=False,
            source="local simulation",
        )
    base = profile["base_url"].rstrip("/")
    if not base:
        raise ProviderError("Save a provider endpoint in Models & souls first.")
    key = config.key(profile)
    if (provider not in ("ollama", "compatible") or profile["api_key_env"]) and not key:
        raise ProviderError(
            f"No credential is configured for {PROVIDERS[provider][0]}. Add it in Models & souls, then retry."
        )
    headers, params = {}, {}
    endpoint = base + ("/api/tags" if provider == "ollama" else "/models")
    if provider == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        params = {"limit": 100}
    elif provider == "gemini":
        headers = {"x-goog-api-key": key}
        params = {"pageSize": 100}
    elif key:
        headers = {"Authorization": "Bearer " + key}
    found, seen_cursors, truncated = {}, set(), False
    deadline = time.monotonic() + 45
    for page in range(10):
        if not alive():
            raise ProviderError("Reply stopped.")
        if time.monotonic() >= deadline:
            truncated = True
            break
        try:
            response = requests.get(
                endpoint,
                headers=headers,
                params=params,
                timeout=(5, 15),
                allow_redirects=False,
            )
        except requests.RequestException:
            raise ProviderError(
                "Could not reach the provider's models API. Check the saved endpoint and connection."
            ) from None
        if response.status_code >= 300:
            hints = {
                401: "Credential rejected.",
                403: "This credential cannot list models.",
                404: "This endpoint does not offer model discovery.",
                429: "Provider rate limit reached.",
            }
            raise ProviderError(
                f"Model list HTTP {response.status_code}. {hints.get(response.status_code, 'Provider model lookup failed.')}"
            )
        try:
            body = response.json()
            rows = body.get("models" if provider in ("gemini", "ollama") else "data")
            if not isinstance(rows, list):
                raise ValueError()
            for row in rows:
                mid = (
                    row.get("name") or row.get("model")
                    if provider == "ollama"
                    else row.get("name")
                    if provider == "gemini"
                    else row.get("id")
                )
                if not isinstance(mid, str) or not mid or len(mid) > 200:
                    raise ValueError()
                mid = mid.removeprefix("models/") if provider == "gemini" else mid
                display = row.get("display_name") or row.get("displayName") or mid
                if not isinstance(display, str):
                    raise ValueError()
                found[mid] = {"id": mid, "name": display[:200]}
                if provider == "gemini":
                    found[mid]["methods"] = [
                        m[:100]
                        for m in row.get("supportedGenerationMethods", [])
                        if isinstance(m, str)
                    ][:20]
                if len(found) >= 2000:
                    truncated = True
                    break
            cursor = (
                body.get("nextPageToken")
                if provider == "gemini"
                else body.get("last_id")
                if body.get("has_more")
                else None
            )
            if body.get("has_more") and not cursor:
                raise ValueError()
            if not cursor or truncated:
                break
            if (
                not isinstance(cursor, str)
                or len(cursor) > 1000
                or cursor in seen_cursors
            ):
                raise ValueError()
            seen_cursors.add(cursor)
            params["pageToken" if provider == "gemini" else "after_id"] = cursor
            truncated = page == 9
        except (ValueError, TypeError, AttributeError):
            raise ProviderError("Provider returned an invalid model list.") from None
    result = dict(
        provider=provider,
        models=sorted(found.values(), key=lambda r: r["id"]),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        truncated=truncated,
        source=endpoint,
    )
    return redact(result, {key})


TOOL_ARGUMENTS = {"get_model_settings": {"profile_id"}, "list_provider_models": {"provider", "profile_id"},
                  **{t["name"]: set(t["parameters"]["properties"]) for t in [*FILE_TOOL_DEFINITIONS, *WEB_TOOL_DEFINITIONS]}}
TOOL_NAMES = list(TOOL_ARGUMENTS)
FILE_TOOL_NAMES = {t["name"] for t in FILE_TOOL_DEFINITIONS}
WEB_TOOL_NAMES = {t["name"] for t in WEB_TOOL_DEFINITIONS}


def tool_allowed(name, settings, profile):
    """A tool is offered only if the project and the model both allow it (None allows all)."""
    if name in WRITE_TOOLS and settings.get("project_access") != "write":
        return False
    return all(chosen is None or name in chosen for chosen in (settings.get("tools"), profile.get("tools")))


class ModelTools:
    definitions = MODEL_TOOL_DEFINITIONS

    def __init__(self, config, settings, alive=lambda: True, profile=None):
        self.config, self.settings, self.alive = config, copy.deepcopy(settings), alive
        self.audit, self.cache = [], {}
        profile = profile or {}
        self.files = FileTools(self.settings, profile, backup_root=Path(config.root) / "backups")
        self.web = WebTools(config.key({"api_key_env": WEB_KEY_NAME}))
        # Web tools are offered only once a Browserbase key is saved.
        self.definitions = [t for t in [*MODEL_TOOL_DEFINITIONS, *FILE_TOOL_DEFINITIONS, *(WEB_TOOL_DEFINITIONS if self.web.key else [])]
                            if tool_allowed(t["name"], self.settings, profile)]

    def execute(self, name, arguments):
        if not self.alive():
            return {"error": "Reply stopped."}
        try:
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            if not isinstance(arguments, dict):
                raise ProviderError("Tool arguments must be an object.")
            allowed = TOOL_ARGUMENTS.get(name, set())
            if (
                name not in {t["name"] for t in self.definitions}
                or set(arguments) - allowed
            ):
                raise ProviderError(
                    "This tool or its arguments are not available."
                )
            profile_id = arguments.get("profile_id")
            if profile_id is not None and (
                not isinstance(profile_id, str) or len(profile_id) > 60
            ):
                raise ProviderError("Invalid profile_id.")
            if name == "get_model_settings":
                result = settings_snapshot(
                    self.config, self.settings, include_instructions=True
                )
                if profile_id:
                    result["models"] = [
                        p for p in result["models"] if p["id"] == profile_id
                    ]
                    if not result["models"]:
                        raise ProviderError("Configured model profile not found.")
            elif name in FILE_TOOL_NAMES:
                result = self.files.execute(name, arguments)
            elif name in WEB_TOOL_NAMES:
                result = self.web.execute(name, arguments)
                # Web pages share the per-completion context budget with file reads.
                size = len(result.get("content", ""))
                if self.files.read_chars + size > self.settings.get("max_context_chars", 80000):
                    raise ProviderError("Reads reached this completion's context limit.")
                self.files.read_chars += size
            else:
                provider = arguments.get("provider")
                if not isinstance(provider, str):
                    raise ProviderError("A provider name is required.")
                cache_key = (provider, profile_id)
                if cache_key not in self.cache:
                    self.cache[cache_key] = list_models(
                        self.config, provider, profile_id, self.settings, self.alive
                    )
                result = self.cache[cache_key]
            self.audit.append(
                {"name": name, "provider": arguments.get("provider"), "ok": True,
                 **({key: result[key] for key in ("path", "sha256", "created", "deleted", "backup") if key in result} if name in ("read_file", *WRITE_TOOLS) else {}),
                 **({key: arguments[key] for key in ("query", "url") if key in arguments} if name in WEB_TOOL_NAMES else {})}
            )
            return result
        except (ProviderError, ValueError, TypeError) as exc:
            # Only locally-authored errors are returned; never echo arbitrary upstream bodies.
            error = (
                str(exc)
                if isinstance(exc, ProviderError)
                else "Invalid tool arguments."
            )
            self.audit.append(
                {
                    "name": name
                    if name in {t["name"] for t in self.definitions}
                    else "unknown",
                    "ok": False,
                }
            )
            return {"error": error}
