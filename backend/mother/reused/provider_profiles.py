"""Named provider *profiles* + role assignment (backlog #7, option B).

A **profile** is a named `{provider, model}` pair (e.g. "haiku" → anthropic /
claude-haiku-4-5-20251001). Two **roles** — `decision` (the LLM that picks
actions) and `vision` (the VLM that reads screenshots) — each point at one
profile. The web UI CRUDs profiles and assigns them to roles.

The runtime (``llm_router`` / ``perception``) still reads plain ``.env`` keys, so
this layer never touches resolution logic: :func:`apply_to_env` **compiles** the
active role assignments down to the exact ``.env`` keys those modules already
read. Profiles hold no secrets — API keys stay in ``.env``, keyed by provider.

Storage is a small ``config.json`` next to ``.env``::

    {"profiles": {"haiku": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}},
     "roles": {"decision": "haiku", "vision": "haiku"}}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("AgentRuntime")

ROLES = ("decision", "vision")

# Per-role .env keys the runtime reads. Decision model is the provider-agnostic
# LLM_MODEL (llm_router._resolve_model checks it first); vision model is
# provider-specific (perception._resolve reads a different var per provider).
_VISION_MODEL_VAR = {
    "anthropic": "ANTHROPIC_VISION_MODEL",
    "gemini": "GEMINI_MODEL",
    "ollama": "VISION_MODEL",
}

# Seeded the first time config.json is read and absent — sensible cloud + local
# starting points, with Haiku (multimodal) driving both roles.
_DEFAULT_PROFILES = {
    "haiku": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    "gemini-vision": {"provider": "gemini", "model": "gemini-2.5-flash-lite"},
    "local": {"provider": "ollama", "model": "qwen3.5:4b"},
}
_DEFAULT_ROLES = {"decision": "haiku", "vision": "haiku"}


def default_config() -> dict:
    """A fresh config with the seed profiles and Haiku assigned to both roles."""
    return {
        "profiles": {k: dict(v) for k, v in _DEFAULT_PROFILES.items()},
        "roles": dict(_DEFAULT_ROLES),
    }


def read_profiles(config_path: Path) -> dict:
    """Load ``config.json`` as ``{"profiles": {...}, "roles": {...}}``.

    A missing or unreadable file yields :func:`default_config`. The result is
    always normalized: ``profiles`` is a dict and ``roles`` has both keys.
    """
    raw: dict = {}
    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "provider profiles: could not read %s (%s); using defaults",
                config_path,
                e,
            )
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        return default_config()
    roles = raw.get("roles") if isinstance(raw.get("roles"), dict) else {}
    return {
        "profiles": {str(k): _norm_profile(v) for k, v in profiles.items()},
        "roles": {r: roles.get(r) for r in ROLES},
    }


def write_profiles(config_path: Path, data: dict) -> None:
    """Persist ``data`` to ``config.json`` (pretty-printed, parent dir created)."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "Wrote %d provider profile(s) to %s", len(data.get("profiles", {})), config_path
    )


def upsert_profile(data: dict, name: str, provider: str, model: str) -> dict:
    """Add or replace the profile ``name``; returns the mutated ``data``."""
    name = name.strip()
    if not name:
        raise ValueError("profile name is required")
    if not provider.strip():
        raise ValueError("provider is required")
    data.setdefault("profiles", {})[name] = {
        "provider": provider.strip().lower(),
        "model": model.strip(),
    }
    return data


def delete_profile(data: dict, name: str) -> dict:
    """Remove profile ``name`` and unassign any role pointing at it."""
    data.get("profiles", {}).pop(name, None)
    roles = data.setdefault("roles", {})
    for role in ROLES:
        if roles.get(role) == name:
            roles[role] = None
    return data


def assign_role(data: dict, role: str, profile_name: str) -> dict:
    """Point ``role`` (``decision``/``vision``) at an existing profile."""
    if role not in ROLES:
        raise ValueError(f"unknown role: {role!r} (expected one of {ROLES})")
    if profile_name not in data.get("profiles", {}):
        raise ValueError(f"no such profile: {profile_name!r}")
    data.setdefault("roles", {})[role] = profile_name
    return data


def apply_to_env(data: dict, env_path: Path) -> dict[str, str]:
    """Compile the active role assignments into ``.env`` and return the updates.

    Writes ``LLM_PROVIDER``/``LLM_MODEL`` for the decision role and
    ``VISION_PROVIDER`` + the provider's vision-model var for the vision role —
    exactly the keys ``llm_router`` and ``perception`` already read. Unassigned
    roles are skipped. Uses ``config_store.write_config`` (preserves comments,
    never wipes omitted secrets).
    """
    from . import config_store

    profiles = data.get("profiles", {})
    roles = data.get("roles", {})
    updates: dict[str, str] = {}

    decision = profiles.get(roles.get("decision"))
    if decision:
        updates["LLM_PROVIDER"] = decision["provider"]
        if decision.get("model"):
            updates["LLM_MODEL"] = decision["model"]

    vision = profiles.get(roles.get("vision"))
    if vision:
        updates["VISION_PROVIDER"] = vision["provider"]
        model = vision.get("model")
        var = _VISION_MODEL_VAR.get(vision["provider"])
        if model and var:
            updates[var] = model

    if updates:
        config_store.write_config(env_path, updates)
    return updates


def _norm_profile(value) -> dict:
    if not isinstance(value, dict):
        return {"provider": "", "model": ""}
    return {
        "provider": str(value.get("provider", "")).strip().lower(),
        "model": str(value.get("model", "")).strip(),
    }
