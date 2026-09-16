"""Bounded text-file access through explicit virtual folder mounts."""

from pathlib import Path, PurePosixPath
import hashlib

from . import workspace
from .providers import ProviderError


FILE_TOOL_DEFINITIONS = [
    {"name": "list_files", "description": "List readable text files in /tools, /docs, or /project. /tools and /docs are system-wide read-only mounts. Does not execute anything.",
     "parameters": {"type": "object", "properties": {"folder": {"type": "string", "enum": ["/tools", "/docs", "/project"]}}, "required": ["folder"], "additionalProperties": False}},
    {"name": "read_file", "description": "Read a bounded UTF-8 text file by virtual path, e.g. /docs/guide.md or /project/src/main.py. Return its content and version hash.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}},
]


class FileTools:
    def __init__(self, settings, profile):
        self.settings, self.profile = settings, profile
        self.roots = {key: value for key, value in settings.get("shared_paths", {}).items() if value}
        if settings.get("project_path"):
            self.roots["project"] = settings["project_path"]
        self.read_chars = 0

    def selected(self):
        if self.profile.get("context_mode") != "files":
            return set()
        selected = set(self.settings.get("context_files", []))
        assigned = self.profile.get("context_files")
        return selected if assigned is None else selected.intersection(assigned)

    def locate(self, value):
        if not isinstance(value, str) or len(value) > 1000 or "\\" in value:
            raise ProviderError("Use a virtual path under /project, /tools or /docs.")
        parts = PurePosixPath(value).parts
        if len(parts) < 2 or parts[0] != "/" or parts[1] not in self.roots or ".." in parts or ":" in value:
            raise ProviderError("Folder is unavailable or the path is outside its mount.")
        mount = parts[1]
        rel = Path(*parts[2:])
        root = workspace.root_path(self.roots[mount])
        path = root / rel
        # Reject links and junctions rather than following a changing alias.
        for current in (path, *path.parents):
            if current == root:
                break
            if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
                raise ProviderError("Linked paths are not accessible through file tools.")
        if not path.resolve().is_relative_to(root):
            raise ProviderError("Path is outside its mount.")
        return mount, rel, path

    def permitted(self, mount, rel):
        return mount != "project" or self.settings.get("project_access", "selected") in ("read", "write") or rel.as_posix() in self.selected()

    def execute(self, name, args):
        try:
            if name == "list_files":
                mount, rel, path = self.locate(args.get("folder"))
                if rel != Path("."):
                    raise ProviderError("List a mount root: /project, /tools or /docs.")
                result = workspace.list_files(str(path))
                rows = [f for f in result["files"] if self.permitted(mount, Path(f["path"]))]
                return {"files": [{**f, "path": f"/{mount}/{f['path']}"} for f in rows[:500]], "truncated": result["truncated"] or len(rows) > 500, "access": "read-only"}
            mount, rel, path = self.locate(args.get("path"))
            if not self.permitted(mount, rel) or not workspace.allowed(rel):
                raise ProviderError("File is excluded or not assigned to this model.")
            if not path.is_file() or path.stat().st_size > 200000:
                raise ProviderError("File is missing or exceeds the 200 KB limit.")
            raw = path.read_bytes()
            body = raw.decode("utf-8-sig")
            if "\x00" in body:
                raise ProviderError("Binary files are not supported.")
            if self.read_chars + len(body) > self.settings.get("max_context_chars", 80000):
                raise ProviderError("File reads reached this completion's context limit.")
            self.read_chars += len(body)
            return {"path": args["path"], "content": body, "sha256": hashlib.sha256(raw).hexdigest(), "access": "read-only"}
        except (OSError, UnicodeError, ValueError):
            raise ProviderError("Cannot read this folder or file. Check its path and text encoding in setup.") from None
