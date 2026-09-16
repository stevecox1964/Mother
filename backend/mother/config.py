import copy
import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import urlparse
from dotenv import dotenv_values
from .reused import config_store, provider_profiles

PROVIDERS = {
    "openai": ("OpenAI", "https://api.openai.com/v1", "OPENAI_API_KEY"),
    "anthropic": ("Anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    "gemini": (
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta",
        "GOOGLE_API_KEY",
    ),
    "ollama": ("Ollama", "http://127.0.0.1:11434", ""),
    "compatible": ("OpenAI-compatible", "", "COMPATIBLE_API_KEY"),
    "demo": ("Demo · simulated responses", "", ""),
}


class Config:
    def __init__(self, root, credentials_root=None, model_limit=16):
        self.model_limit = model_limit
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "config.json"
        self.env = Path(credentials_root or root) / ".env"
        self.lock = threading.RLock()
        if not self.path.exists():
            seeds = provider_profiles.default_config()["profiles"]
            models = [
                self.profile(
                    "chief",
                    "Chief",
                    "openai",
                    "gpt-6-astra",
                    "Answer the user clearly and concisely. Use evidence when relevant.",
                ),
                self.profile(
                    "critic",
                    "Critic",
                    seeds["haiku"]["provider"],
                    seeds["haiku"]["model"],
                    "Challenge assumptions. Find failure cases and missing tests.",
                ),
                self.profile(
                    "custodian",
                    "Code custodian",
                    "gemini",
                    "gemini-2.5-flash",
                    "Explain the selected code accurately. Cite file paths. Answer peers.",
                ),
                self.profile(
                    "local",
                    "Local thinker",
                    "ollama",
                    seeds["local"]["model"],
                    "Offer a concise independent perspective.",
                ),
            ]
            models[2]["context_mode"] = "files"
            models[3]["enabled"] = False
            self.save(
                {
                    "models": models,
                    "chief_id": "chief",
                    "rounds": 1,
                    "project_path": "",
                    "context_files": [],
                    "max_context_chars": 80000,
                }
            )

    @staticmethod
    def profile(id, name, provider, model, soul):
        return dict(
            id=id,
            name=name,
            provider=provider,
            model=model,
            soul=soul,
            enabled=True,
            context_mode="board",
            vision=False,
            tools_enabled=True,
            expertise="",
            context_files=None,
            base_url=PROVIDERS[provider][1],
            api_key_env=PROVIDERS[provider][2],
            max_tokens=4096,
        )

    def read(self):
        with self.lock:
            return json.loads(self.path.read_text(encoding="utf-8"))

    def key(self, profile):
        name = profile.get("api_key_env", "")
        if not name:
            return ""
        return str(
            dotenv_values(self.env, interpolate=False).get(name)
            or os.environ.get(name, "")
            or ""
        )

    def public(self, settings=None):
        data = copy.deepcopy(settings) if settings is not None else self.read()
        for p in data["models"]:
            p["key_set"] = bool(self.key(p))
            p["ready"] = bool(p["model"]) and (
                p["provider"] in ("demo", "ollama")
                or p["key_set"]
                or (p["provider"] == "compatible" and not p["api_key_env"])
            )
        data["providers"] = [
            dict(id=k, name=v[0], base_url=v[1], api_key_env=v[2])
            for k, v in PROVIDERS.items()
        ]
        data["storage_path"] = str(self.root)
        return data

    def save(self, raw):
        data = copy.deepcopy(raw)
        models = data.get("models")
        if not isinstance(models, list) or len(models) > self.model_limit:
            raise ValueError(f"Use up to {self.model_limit} model profiles.")
        ids = set()
        clean = []
        for p in models:
            if not isinstance(p, dict):
                raise ValueError("Invalid model profile.")
            mid = str(p.get("id", ""))
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", mid) or mid in ids:
                raise ValueError(
                    "Model IDs must be unique letters, numbers, underscores or hyphens."
                )
            ids.add(mid)
            provider = p.get("provider")
            if provider not in PROVIDERS:
                raise ValueError("Unknown provider.")
            name = str(p.get("name", "")).strip()
            if not name or len(name) > 80:
                raise ValueError("Model name is required (up to 80 characters).")
            model = str(p.get("model", "")).strip()
            if len(model) > 200:
                raise ValueError("Model ID is too long.")
            soul = str(p.get("soul", ""))
            if len(soul) > 20000:
                raise ValueError("Soul must be under 20,000 characters.")
            mode = p.get("context_mode", "board")
            if mode not in ("board", "files"):
                raise ValueError("Invalid context mode.")
            expertise = str(p.get("expertise", "")).strip()
            if len(expertise) > 4000:
                raise ValueError("Expertise must be under 4,000 characters.")
            assigned = p.get("context_files")
            if assigned is not None and (
                not isinstance(assigned, list)
                or len(assigned) > 100
                or any(not isinstance(f, str) for f in assigned)
            ):
                raise ValueError(
                    "Model file assignments must be a list of up to 100 paths."
                )
            env = str(p.get("api_key_env", "")).strip()
            if env and (
                not re.fullmatch(r"[A-Z][A-Z0-9_]{0,100}", env)
                or not config_store.is_secret(env)
            ):
                raise ValueError(
                    "Credential variable must be uppercase and contain API_KEY, TOKEN or SECRET."
                )
            base = str(p.get("base_url", "")).strip().rstrip("/")
            if provider != "demo":
                u = urlparse(base)
                if (
                    u.scheme not in ("http", "https")
                    or not u.hostname
                    or u.username
                    or u.password
                    or u.query
                    or u.fragment
                ):
                    raise ValueError(
                        "Use an HTTP(S) base URL without credentials, query or fragment."
                    )
                if u.scheme == "http" and u.hostname not in (
                    "localhost",
                    "127.0.0.1",
                    "::1",
                ):
                    raise ValueError("Remote provider endpoints require HTTPS.")
            tokens = int(p.get("max_tokens", 4096))
            if not 128 <= tokens <= 32768:
                raise ValueError("Output token limit must be 128–32768.")
            clean.append(
                dict(
                    **({"system_model_id": str(p["system_model_id"])} if p.get("system_model_id") else {}),
                    id=mid,
                    name=name,
                    name_alias=str(p.get("name_alias", "") or "").strip()[:80],
                    provider=provider,
                    model=model,
                    soul=soul,
                    context_mode=mode,
                    expertise=expertise,
                    context_files=assigned,
                    api_key_env=env,
                    base_url=base,
                    max_tokens=tokens,
                    enabled=bool(p.get("enabled", True)),
                    vision=bool(p.get("vision", False)),
                    tools_enabled=bool(p.get("tools_enabled", True)),
                )
            )
        chief = str(data.get("chief_id", ""))
        if chief and chief not in ids:
            raise ValueError("Chief must be an existing model.")
        rounds = int(data.get("rounds", 2))
        if not 1 <= rounds <= 3:
            raise ValueError("Discussion rounds must be 1–3.")
        cap = int(data.get("max_context_chars", 80000))
        if not 1000 <= cap <= 200000:
            raise ValueError("Context limit must be 1,000–200,000 characters.")
        files = data.get("context_files", [])
        if (
            not isinstance(files, list)
            or len(files) > 100
            or any(not isinstance(f, str) for f in files)
        ):
            raise ValueError("Select up to 100 source files.")
        shared = data.get("shared_paths", {})
        if not isinstance(shared, dict) or set(shared) - {"tools", "docs"} or any(not isinstance(v, str) or len(v) > 1000 for v in shared.values()):
            raise ValueError("Shared folders must contain tools and docs paths.")
        result = dict(
            models=clean,
            chief_id=chief,
            rounds=rounds,
            project_path=str(data.get("project_path", "")).strip(),
            context_files=files,
            max_context_chars=cap,
            shared_paths={name: shared.get(name, "").strip() for name in ("tools", "docs")},
            project_access=data.get("project_access", "selected"),
        )
        if result["project_access"] not in ("selected", "read", "write"):
            raise ValueError("Choose selected files, read-only or read/write project access.")
        with self.lock:
            temp = self.path.with_suffix(".tmp")
            provider_profiles.write_profiles(temp, result)
            temp.replace(self.path)
        return result

    def save_key(self, name, value):
        if not re.fullmatch(
            r"[A-Z][A-Z0-9_]{0,100}", name
        ) or not config_store.is_secret(name):
            raise ValueError("Invalid credential variable name.")
        if (
            not isinstance(value, str)
            or any(c.isspace() for c in value)
            or any(c in value for c in "\"'\\#")
        ):
            raise ValueError("Credential must be a single unquoted token.")
        with self.lock:
            config_store.write_config(self.env, {name: value})
