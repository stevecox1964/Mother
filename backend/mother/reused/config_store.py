from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("AgentRuntime")

# A key is secret if its name contains any of these — its value is never read
# back out to a UI, only its set/unset status.
_SECRET_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD")


def is_secret(key: str) -> bool:
    """True if ``key`` names a credential whose value must never be displayed.

    Examples: ``is_secret("ANTHROPIC_API_KEY")`` → True;
    ``is_secret("LLM_PROVIDER")`` → False.
    """
    up = key.upper()
    return any(marker in up for marker in _SECRET_MARKERS)


def _parse(text: str) -> list[tuple[str, str]]:
    """Return [(key, value)] for every ``KEY=VALUE`` line, ignoring comments."""
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        pairs.append((key.strip(), value.strip()))
    return pairs


def read_config(env_path: Path) -> dict[str, dict]:
    """Read ``.env`` into ``{key: {"value", "is_secret", "set"}}``.

    Secrets (see :func:`is_secret`) always report ``value=None`` — only whether
    they are ``set`` (non-empty) is exposed, so credentials never leak to a UI.
    Non-secret keys expose their value. A missing file yields ``{}``.

    Example return::

        {"LLM_PROVIDER": {"value": "ollama", "is_secret": False, "set": True},
         "ANTHROPIC_API_KEY": {"value": None, "is_secret": True, "set": True}}
    """
    if not env_path.exists():
        return {}
    out: dict[str, dict] = {}
    for key, value in _parse(env_path.read_text(encoding="utf-8")):
        secret = is_secret(key)
        out[key] = {
            "value": None if secret else value,
            "is_secret": secret,
            "set": bool(value),
        }
    return out


def setup_status(env_path: Path) -> dict:
    """First-run readiness check for the web cockpit (backlog #13.1).

    Returns ``{"env_exists": bool, "provider_ready": bool, "ready": bool}``.
    ``provider_ready`` is True when the configured ``LLM_PROVIDER`` is
    ``ollama`` (no key needed) or any ``*_API_KEY``-style key (see
    :func:`is_secret`) is set to a non-empty value. A missing ``.env`` yields
    all False. Never raises — a bad/missing file is just "not ready".

    Example: ``setup_status(Path("Python/.env"))`` ->
    ``{"env_exists": True, "provider_ready": True, "ready": True}``.
    """
    try:
        if not env_path.exists():
            return {"env_exists": False, "provider_ready": False, "ready": False}
        config = read_config(env_path)
        provider = (config.get("LLM_PROVIDER", {}).get("value") or "").strip().lower()
        has_key = any(
            "API_KEY" in key.upper() and item.get("set") for key, item in config.items()
        )
        provider_ready = provider == "ollama" or has_key
        return {
            "env_exists": True,
            "provider_ready": provider_ready,
            "ready": provider_ready,
        }
    except Exception:
        logger.exception(f"setup_status failed for {env_path}")
        return {"env_exists": False, "provider_ready": False, "ready": False}


def write_config(env_path: Path, updates: dict[str, str]) -> None:
    """Apply ``updates`` to ``.env`` in place, preserving comments and order.

    Existing keys are rewritten where they sit; new keys are appended. Keys not
    in ``updates`` are left untouched — so a settings form that omits a secret
    (because it never received the value) cannot wipe it. Pass ``None`` as a
    value to skip a key explicitly.

    Example: ``write_config(path, {"LLM_PROVIDER": "ollama"})``.
    """
    pending = {k: v for k, v in updates.items() if v is not None}
    lines = (
        env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    )

    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in pending:
                out.append(f"{key}={pending[key]}")
                seen.add(key)
                continue
        out.append(line)

    for key, value in pending.items():
        if key not in seen:
            out.append(f"{key}={value}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    logger.info(f"Wrote {len(pending)} config key(s) to {env_path}")
