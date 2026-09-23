import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SKIP = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    "data",
    ".next",
    ".idea",
    ".vscode",
    ".aws",
    ".ssh",
    ".azure",
    "artifacts",
}
EXT = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".html",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".sql",
    ".rs",
    ".go",
    ".c",
    ".cpp",
    ".h",
    ".cs",
    ".sh",
    ".ps1",
}

# Binary files the Files page can show and upload. Models do not read them.
MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}
MAX_MEDIA_BYTES = 8 * 1024 * 1024


def allowed(path, media=False):
    return (
        not any(part.lower() in SKIP for part in path.parts)
        and (path.suffix.lower() in EXT or (media and path.suffix.lower() in MEDIA))
        and not any(
            word in path.name.lower()
            for word in (
                ".env",
                "secret",
                "credential",
                "lock.json",
                "package-lock",
                "token",
                "password",
            )
        )
    )


def root_path(raw):
    root = Path(raw).expanduser().resolve()
    if not raw or not root.is_dir():
        raise ValueError("Choose an existing project folder.")
    return root


def list_files(raw, media=False):
    root = root_path(raw)
    result = []
    visited = 0
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d.lower() not in SKIP
            and not (Path(folder) / d).is_symlink()
            and not (
                hasattr(Path(folder) / d, "is_junction")
                and (Path(folder) / d).is_junction()
            )
        )
        for name in sorted(files):
            p = Path(folder) / name
            rel = p.relative_to(root)
            visited += 1
            if visited > 20000:
                return {"files": result, "truncated": True}
            try:
                if (
                    allowed(rel, media)
                    and not p.is_symlink()
                    and p.resolve().is_relative_to(root)
                    and p.stat().st_size
                    <= (MAX_MEDIA_BYTES if p.suffix.lower() in MEDIA else 200000)
                ):
                    result.append({"path": rel.as_posix(), "bytes": p.stat().st_size})
            except OSError:
                continue
            if len(result) >= 2000:
                return {"files": result, "truncated": True}
    return {"files": result, "truncated": False}


def snapshot(config, *, include_bodies=False):
    if not config["context_files"]:
        return "", []
    root = root_path(config["project_path"])
    parts = []
    manifest = []
    total = 0
    for rel in config["context_files"]:
        path = (root / rel).resolve()
        if (
            not path.is_relative_to(root)
            or not allowed(Path(rel))
            or not path.is_file()
        ):
            raise ValueError(f"File is outside the project or excluded: {rel}")
        if path.stat().st_size > 200000:
            raise ValueError(f"File too large: {rel}")
        raw = path.read_bytes()
        try:
            body = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError(f"File is not UTF-8 text: {rel}")
        if "\x00" in body:
            raise ValueError(f"Binary file excluded: {rel}")
        text = f"\n--- FILE: {rel} ---\n{body}\n--- END FILE ---\n"
        total += len(text)
        if total > config["max_context_chars"]:
            raise ValueError(
                "Selected files exceed the context limit. Select fewer files or increase the limit."
            )
        parts.append(text)
        manifest.append(
            {
                "path": rel,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                **({"body": body} if include_bodies else {}),
            }
        )
    return "".join(parts), manifest


def model_snapshots(settings, profiles):
    """Read selected files once, then distribute only each profile's assigned subset."""
    selected = settings["context_files"]
    needed = {
        f
        for p in profiles
        if p["context_mode"] == "files"
        for f in (selected if p.get("context_files") is None else p["context_files"])
        if f in selected
    }
    _, source = snapshot(
        {**settings, "context_files": [f for f in selected if f in needed]},
        include_bodies=True,
    )
    code, manifests = {}, {}
    for p in profiles:
        assigned = selected if p.get("context_files") is None else p["context_files"]
        files = [
            f for f in source if p["context_mode"] == "files" and f["path"] in assigned
        ]
        code[p["id"]] = "".join(
            f"\n--- FILE: {f['path']} ---\n{f['body']}\n--- END FILE ---\n"
            for f in files
        )
        manifests[p["id"]] = files
    return code, manifests


MAGIC = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
    ".pdf": (b"%PDF-",),
}


def project_file(raw, rel, media=False):
    """Resolve a user-given relative path inside the project, or raise."""
    root = root_path(raw)
    parts = PurePosixPath(rel).parts if isinstance(rel, str) else ()
    if (
        not parts
        or len(rel) > 1000
        or any(c in rel for c in '\\:*?"<>|')
        or any(ord(c) < 32 for c in rel)
        or rel.startswith("/")
        or ".." in parts
        or not allowed(Path(*parts), media)
    ):
        raise ValueError(f"File is outside the project or excluded: {rel}")
    path = root / Path(*parts)
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError(f"File is outside the project or excluded: {rel}")
    return root, path


def check_upload(rel, data):
    """Refuse content that the Files page and models could not use safely."""
    suffix = Path(rel).suffix.lower()
    if suffix in MEDIA:
        if len(data) > MAX_MEDIA_BYTES:
            raise ValueError(f"Images and PDFs must be 8 MB or smaller: {rel}")
        if not data.startswith(MAGIC[suffix]) or (
            suffix == ".webp" and data[8:12] != b"WEBP"
        ):
            raise ValueError(f"File content does not match its {suffix} name: {rel}")
        return
    if len(data) > 200000:
        raise ValueError(f"Text files must be 200 KB or smaller: {rel}")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError(f"File is not UTF-8 text: {rel}")
    if "\x00" in text:
        raise ValueError(f"Binary file excluded: {rel}")


def save_upload(raw, rel, data, backup_root):
    """Write an uploaded file. Keep a backup when it replaces a file."""
    root, path = project_file(raw, rel, media=True)
    check_upload(rel, data)
    backup = None
    if path.exists():
        if not path.is_file():
            raise ValueError(f"A folder already uses this name: {rel}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = Path(backup_root) / stamp / Path(rel)
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(path.read_bytes())
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.parent.resolve().is_relative_to(root):
        raise ValueError(f"File is outside the project or excluded: {rel}")
    temp = path.with_name(f".{path.name}.mother-tmp")
    temp.write_bytes(data)
    os.replace(temp, path)
    return {"path": rel, "bytes": len(data), "replaced": backup is not None,
            **({"backup": str(backup)} if backup else {})}
