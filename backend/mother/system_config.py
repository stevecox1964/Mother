"""Machine-wide model connections with independent project bindings."""

import copy
import hashlib

from .config import Config

CONNECTION_FIELDS = ("provider", "model", "base_url", "api_key_env", "vision")


class SystemConfig:
    def __init__(self, projects):
        self.projects = projects
        root = projects.store.root
        path = root / "system" / "config.json"
        fresh = not path.exists()
        self.config = Config(path.parent, credentials_root=root, model_limit=64)
        if fresh:
            registry, bindings = {}, []
            for project in projects.store.projects():
                cfg = projects.config(project["id"])
                settings = cfg.read()
                for profile in settings["models"]:
                    signature = tuple(profile[field] for field in CONNECTION_FIELDS)
                    entry = next((p for p in registry.values() if tuple(p[f] for f in CONNECTION_FIELDS) == signature), None)
                    if entry is None:
                        mid = profile["id"]
                        if mid in registry:
                            mid = mid[:45] + "-" + hashlib.sha256(repr(signature).encode()).hexdigest()[:10]
                        entry = {**profile, "id": mid, "enabled": True}
                        entry.pop("system_model_id", None)
                        registry[mid] = entry
                    profile["system_model_id"] = entry["id"]
                bindings.append((cfg, settings))
            self.config.save({**self.config.read(), "models": list(registry.values()), "chief_id": next(iter(registry), "")})
            for cfg, settings in bindings:
                backup = cfg.path.with_suffix(".pre-system.json")
                if not backup.exists():
                    backup.write_bytes(cfg.path.read_bytes())
                cfg.save(settings)

    def adopt_registry_names(self):
        """One-time repair for configs written before per-project name overrides.

        Those names were copies made by the registry migration, not deliberate
        aliases, so they went stale whenever System setup renamed a model. Adopt
        the registry name, keeping a real alias only where two profiles in the
        same project would otherwise collide.
        """
        registry = {p["id"]: p for p in self.config.read()["models"]}
        for project in self.projects.store.projects():
            cfg = self.projects.config(project["id"])
            settings = cfg.read()
            if all("name_alias" in p or not p.get("system_model_id") for p in settings["models"]):
                continue
            backup = cfg.path.with_suffix(".pre-names.json")
            if not backup.exists():
                backup.write_bytes(cfg.path.read_bytes())
            taken = {p["name"] for p in settings["models"] if not p.get("system_model_id")}
            kept = []
            for profile in settings["models"]:
                sid = profile.get("system_model_id")
                if not sid:
                    kept.append(profile)
                    continue
                if sid not in registry:
                    continue  # the connection was deleted in System setup
                if "name_alias" not in profile:
                    name = registry[sid]["name"]
                    # Two souls can share one connection; keep them tellable apart.
                    profile["name_alias"] = profile["name"] if name in taken else ""
                    profile["name"] = profile["name_alias"] or name
                taken.add(profile["name"])
                kept.append(profile)
            settings["models"] = kept
            if settings.get("chief_id") not in {m["id"] for m in kept}:
                settings["chief_id"] = kept[0]["id"] if kept else ""
            cfg.save(settings)

    def resolve(self, settings):
        result = copy.deepcopy(settings)
        system = self.config.read()
        registry = {p["id"]: p for p in system["models"]}
        for profile in result["models"]:
            sid = profile.get("system_model_id")
            if not sid:
                continue
            source = registry.get(sid)
            profile["system_missing"] = source is None
            profile["system_enabled"] = bool(source and source["enabled"])
            profile["project_enabled"] = profile["enabled"]
            if source:
                profile.update({field: source[field] for field in CONNECTION_FIELDS})
                # An empty alias means this project follows the registry name.
                profile["system_name"] = source["name"]
                profile["name"] = profile.get("name_alias") or source["name"]
            profile["enabled"] = profile["enabled"] and profile["system_enabled"]
        result["shared_paths"] = system.get("shared_paths", {})
        return result

    def save_system(self, data):
        """Save the registry, then carry renames and deletions into every project."""
        before = {p["id"]: p for p in self.config.read()["models"]}
        saved = self.config.save(data)
        after = {p["id"]: p for p in saved["models"]}
        for project in self.projects.store.projects():
            cfg = self.projects.config(project["id"])
            settings = cfg.read()
            kept, changed = [], False
            for profile in settings["models"]:
                sid = profile.get("system_model_id")
                if not sid:
                    kept.append(profile)
                    continue
                if sid not in after:
                    # The connection is gone, so the project binding goes with it.
                    changed = True
                    continue
                alias = profile.get("name_alias")
                if alias is None:
                    # Legacy profile: a name matching the old registry was following it.
                    old_name = before.get(sid, {}).get("name")
                    alias = "" if profile.get("name") == old_name else profile.get("name", "")
                profile["name_alias"] = alias
                name = alias or after[sid]["name"]
                changed = changed or name != profile.get("name")
                profile["name"] = name
                kept.append(profile)
            if not changed:
                continue
            settings["models"] = kept
            if settings.get("chief_id") not in {m["id"] for m in kept}:
                settings["chief_id"] = kept[0]["id"] if kept else ""
            cfg.save(settings)
        return saved

    def save_project(self, pid, settings):
        cfg = self.projects.config(pid)
        old = {p["id"]: p for p in cfg.read()["models"]}
        registry = {p["id"]: p for p in self.config.read()["models"]}
        settings = copy.deepcopy(settings)
        for profile in settings.get("models", []):
            sid = profile.get("system_model_id")
            previous = old.get(profile.get("id"), {})
            if not sid and previous.get("system_model_id"):
                raise ValueError("A project model must keep its system connection.")
            if not sid and not previous:
                raise ValueError("Add the model in System setup before assigning it to a project.")
            if sid and sid not in registry and sid != previous.get("system_model_id"):
                raise ValueError("System model no longer exists. Refresh System setup.")
            if sid in registry:
                profile.update({field: registry[sid][field] for field in CONNECTION_FIELDS})
                # Store a name only while it differs from the registry.
                name = str(profile.get("name", "") or "").strip()
                profile["name_alias"] = "" if name == registry[sid]["name"] else name
            if "project_enabled" in profile:
                profile["enabled"] = profile.pop("project_enabled")
        # Shared roots are owned solely by System setup.
        settings["shared_paths"] = cfg.read().get("shared_paths", {})
        cfg.save(settings)
