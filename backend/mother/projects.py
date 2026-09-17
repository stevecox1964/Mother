"""Project metadata and isolated configuration; credentials stay machine-local."""

import copy
import threading
from pathlib import Path

from .config import Config
from .store import now, uid


PROJECT_TYPES = ("coding", "research", "writing", "general")
MOTHER_PROJECT_ID = "mother"
MOTHER_DOCUMENTS = {
    "architecture": ("Mother architecture", "docs/MOTHER_KNOWLEDGE_MODEL_ARCHITECTURE.md"),
    "review": ("Architecture review & next steps", "docs/MOTHER_ARCHITECTURE_REVIEW.md"),
}


class Projects:
    def __init__(self, store, default_config, repository_root=None):
        self.store = store
        self.repository_root = Path(repository_root or Path(__file__).resolve().parents[2]).resolve()
        self.configs = {"default": default_config}
        self.lock = threading.RLock()
        self.ensure_mother_project(default_config)
        for project in store.projects():
            self.prepare_folders(project["id"])
        from .system_config import SystemConfig
        self.system = SystemConfig(self)
        self.system.adopt_registry_names()

    def read(self, pid):
        return self.system.resolve(self.config(pid).read())

    def ensure_mother_project(self, default_config):
        if self.store.project(MOTHER_PROJECT_ID):
            return
        folder = self.store.root / "projects" / MOTHER_PROJECT_ID
        cfg = Config(folder, credentials_root=self.store.root)
        settings = copy.deepcopy(default_config.read())
        selected = [path for _, path in MOTHER_DOCUMENTS.values() if (self.repository_root / path).is_file()]
        settings.update(project_path=str(self.repository_root), context_files=selected,
                        max_context_chars=max(80000, settings["max_context_chars"]))
        for model in settings["models"]:
            model.update(context_mode="files", context_files=None)
        cfg.save(settings)
        with self.store.connect() as db:
            db.execute("INSERT INTO projects (id,name,type,created_at) VALUES (?,?,?,?)", (MOTHER_PROJECT_ID, "Mother", "coding", now()))
        self.configs[MOTHER_PROJECT_ID] = cfg

    def prepare_folders(self, pid):
        folder = self.store.project_folder(pid)
        for name in ("workspace", "conversations", "attachments"):
            (folder / name).mkdir(parents=True, exist_ok=True)
        return folder

    def config(self, pid):
        with self.lock:
            folder = self.store.project_folder(pid)
            if pid not in self.configs:
                self.configs[pid] = Config(folder, credentials_root=self.store.root)
            return self.configs[pid]

    def public(self, project):
        folder = self.store.project_folder(project["id"])
        storage = self.store.root if project["id"] == "default" else folder
        main = project["id"] == MOTHER_PROJECT_ID
        return {
            **project, "is_main": main,
            "purpose": "Develop and maintain Mother itself." if main else "",
            "storage_path": str(storage),
            "workspace_path": str(self.repository_root if main else folder / "workspace"),
            "documents": [
                {"id": key, "title": title, "path": path}
                for key, (title, path) in MOTHER_DOCUMENTS.items()
                if main and (self.repository_root / path).is_file()
            ],
        }

    def document(self, pid, key):
        if pid != MOTHER_PROJECT_ID or key not in MOTHER_DOCUMENTS:
            raise ValueError("Project document not found.")
        title, path = MOTHER_DOCUMENTS[key]
        from .workspace import snapshot
        _, manifest = snapshot({"project_path": str(self.repository_root),
                                "context_files": [path], "max_context_chars": 200000},
                               include_bodies=True)
        return {"title": title, "path": path, "content": manifest[0]["body"]}

    @staticmethod
    def validate(data):
        name = data.get("name", "")
        kind = data.get("type", "general")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise ValueError("Project name must contain 1–100 characters.")
        if kind not in PROJECT_TYPES:
            raise ValueError("Choose coding, research, writing or general.")
        return name.strip(), kind

    def create(self, data, source="default"):
        name, kind = self.validate(data)
        # Copy once: later edits never flow between projects.
        settings = copy.deepcopy(self.config(source).read())
        pid = uid()
        folder = self.store.root / "projects" / pid
        settings.update(project_path=str(folder / "workspace"), context_files=[])
        for model in settings["models"]:
            model["context_files"] = None
        cfg = Config(folder, credentials_root=self.store.root)
        cfg.save(settings)
        row = dict(id=pid, name=name, type=kind, created_at=now())
        with self.lock, self.store.connect() as db:
            db.execute("INSERT INTO projects (id,name,type,created_at) VALUES (:id,:name,:type,:created_at)", row)
            self.configs[pid] = cfg
        self.prepare_folders(pid)
        return self.public(row)

    def delete(self, pid):
        if pid in (MOTHER_PROJECT_ID, "default"):
            raise ValueError("Built-in projects cannot be deleted.")
        return self.store.delete_project(pid)

    def restore(self, pid):
        if not self.store.restore_project(pid):
            return None
        self.prepare_folders(pid)
        return self.public(self.store.project(pid))

    def update(self, pid, data):
        self.store.project_folder(pid)
        if pid == MOTHER_PROJECT_ID:
            raise ValueError("Mother is the built-in main project for system development.")
        name, kind = self.validate(data)
        with self.store.connect() as db:
            db.execute("UPDATE projects SET name=?,type=? WHERE id=?", (name, kind, pid))
        return self.public(self.store.project(pid))
