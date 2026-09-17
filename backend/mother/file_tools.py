"""Bounded text-file access through explicit virtual folder mounts."""

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import hashlib
import os
import threading

from . import workspace
from .providers import ProviderError


MAX_FILE_BYTES = 200000
WRITE_TOOLS = {"write_file", "edit_file", "delete_file"}
# One lock for every check-then-write so concurrent models cannot interleave.
WRITE_LOCK = threading.Lock()

FILE_TOOL_DEFINITIONS = [
    {"name": "list_files", "description": "List readable text files in /tools, /docs, or /project. /tools and /docs are system-wide read-only mounts. Does not execute anything.",
     "parameters": {"type": "object", "properties": {"folder": {"type": "string", "enum": ["/tools", "/docs", "/project"]}}, "required": ["folder"], "additionalProperties": False}},
    {"name": "read_file", "description": "Read a bounded UTF-8 text file by virtual path, e.g. /docs/guide.md or /project/src/main.py. Return its content and version hash.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}},
    {"name": "search_files", "description": "Find lines containing text (case-insensitive) in readable files of /tools, /docs, or /project. Return path, line number and line.",
     "parameters": {"type": "object", "properties": {"folder": {"type": "string", "enum": ["/tools", "/docs", "/project"]}, "text": {"type": "string"}}, "required": ["folder", "text"], "additionalProperties": False}},
    {"name": "write_file", "description": "Create or replace a UTF-8 text file under /project. To replace an existing file, pass expected_sha256 from your latest read_file; pass null only to create a new file. Mother keeps a backup of the old version.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "expected_sha256": {"type": ["string", "null"]}}, "required": ["path", "content", "expected_sha256"], "additionalProperties": False}},
    {"name": "edit_file", "description": "Replace one exact, unique occurrence of old_text with new_text in a file under /project. Pass expected_sha256 from your latest read_file. Mother keeps a backup of the old version.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}, "expected_sha256": {"type": "string"}}, "required": ["path", "old_text", "new_text", "expected_sha256"], "additionalProperties": False}},
    {"name": "delete_file", "description": "Delete one text file under /project. Pass expected_sha256 from your latest read_file. Mother keeps a backup of the deleted file.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "expected_sha256": {"type": "string"}}, "required": ["path", "expected_sha256"], "additionalProperties": False}},
]


class FileTools:
    def __init__(self, settings, profile, backup_root=None):
        self.settings, self.profile = settings, profile
        self.roots = {key: value for key, value in settings.get("shared_paths", {}).items() if value}
        if settings.get("project_path"):
            self.roots["project"] = settings["project_path"]
        self.backup_root = Path(backup_root) if backup_root else None
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

    def readable(self, mount, rel, path):
        if not self.permitted(mount, rel) or not workspace.allowed(rel):
            raise ProviderError("File is excluded or not assigned to this model.")
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise ProviderError("File is missing or exceeds the 200 KB limit.")
        raw = path.read_bytes()
        body = raw.decode("utf-8-sig")
        if "\x00" in body:
            raise ProviderError("Binary files are not supported.")
        return raw, body

    def execute(self, name, args):
        try:
            if name in WRITE_TOOLS:
                return self.write(name, args)
            if name in ("list_files", "search_files"):
                mount, rel, path = self.locate(args.get("folder"))
                if rel != Path("."):
                    raise ProviderError("List a mount root: /project, /tools or /docs.")
                result = workspace.list_files(str(path))
                rows = [f for f in result["files"] if self.permitted(mount, Path(f["path"]))]
                if name == "list_files":
                    return {"files": [{**f, "path": f"/{mount}/{f['path']}"} for f in rows[:500]], "truncated": result["truncated"] or len(rows) > 500}
                return self.search(mount, path, rows, args.get("text"), result["truncated"])
            mount, rel, path = self.locate(args.get("path"))
            raw, body = self.readable(mount, rel, path)
            if self.read_chars + len(body) > self.settings.get("max_context_chars", 80000):
                raise ProviderError("File reads reached this completion's context limit.")
            self.read_chars += len(body)
            return {"path": args["path"], "content": body, "sha256": hashlib.sha256(raw).hexdigest()}
        except (OSError, UnicodeError, ValueError):
            raise ProviderError("Cannot read or write this folder or file. Check its path and text encoding in setup.") from None

    def search(self, mount, root, rows, text, truncated):
        if not isinstance(text, str) or not 1 <= len(text) <= 200:
            raise ProviderError("Search text must be 1–200 characters.")
        needle, matches = text.lower(), []
        for row in rows:
            try:
                _, body = self.readable(mount, Path(row["path"]), root / row["path"])
            except (ProviderError, OSError, UnicodeError):
                continue
            for number, line in enumerate(body.splitlines(), 1):
                if needle in line.lower():
                    matches.append({"path": f"/{mount}/{row['path']}", "line": number, "text": line[:300]})
                    if len(matches) >= 100:
                        return {"matches": matches, "truncated": True}
        return {"matches": matches, "truncated": truncated}

    def write(self, name, args):
        if self.backup_root is None:
            raise ProviderError("File writing is not configured for this project.")
        mount, rel, path = self.locate(args.get("path"))
        if mount != "project" or self.settings.get("project_access") != "write":
            raise ProviderError("Writing needs read/write project access and a path under /project.")
        if not workspace.allowed(rel):
            raise ProviderError("This file type or folder cannot be written.")
        # Shared folders stay read-only even when they overlap the project folder.
        for key, raw_root in self.roots.items():
            if key != "project" and path.resolve().is_relative_to(Path(raw_root).expanduser().resolve()):
                raise ProviderError("Shared folders cannot be written.")
        expected = args.get("expected_sha256")
        if expected is not None and not isinstance(expected, str):
            raise ProviderError("expected_sha256 must be a string.")
        with WRITE_LOCK:
            old_raw = None
            if path.exists():
                old_raw, old_body = self.readable(mount, rel, path)
                if expected != hashlib.sha256(old_raw).hexdigest():
                    raise ProviderError("File changed since your last read, or you did not read it. Read it again, then retry with its sha256.")
            elif name == "delete_file":
                raise ProviderError("File does not exist.")
            elif expected is not None:
                raise ProviderError("File does not exist; pass null expected_sha256 to create it.")
            if name == "delete_file":
                content = None
            elif name == "write_file":
                content = args.get("content")
                if not isinstance(content, str):
                    raise ProviderError("content must be a string.")
            else:
                old_text, new_text = args.get("old_text"), args.get("new_text")
                if old_raw is None:
                    raise ProviderError("File is missing; use write_file to create it.")
                if not isinstance(old_text, str) or not isinstance(new_text, str) or not old_text:
                    raise ProviderError("old_text and new_text must be strings; old_text cannot be empty.")
                count = old_body.count(old_text)
                if count != 1:
                    raise ProviderError(f"old_text must appear exactly once; found {count}.")
                content = old_body.replace(old_text, new_text)
            if content is not None:
                new_raw = content.encode("utf-8")
                if len(new_raw) > MAX_FILE_BYTES or "\x00" in content:
                    raise ProviderError("Content must be text under the 200 KB limit.")
            backup = None
            if old_raw is not None:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                backup = self.backup_root / stamp / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(old_raw)
            if content is None:
                path.unlink()
                return {"path": args["path"], "deleted": True, "backup": str(backup)}
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.resolve().is_relative_to(workspace.root_path(self.roots["project"])):
                raise ProviderError("Path is outside its mount.")
            temp = path.with_name(f".{path.name}.mother-tmp")
            temp.write_bytes(new_raw)
            os.replace(temp, path)
        return {"path": args["path"], "created": old_raw is None, "bytes": len(new_raw),
                "sha256": hashlib.sha256(new_raw).hexdigest(),
                **({"backup": str(backup)} if backup else {})}
