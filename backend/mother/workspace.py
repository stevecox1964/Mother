import hashlib
import os
from pathlib import Path

SKIP = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
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


def allowed(path):
    return (
        not any(part.lower() in SKIP for part in path.parts)
        and path.suffix.lower() in EXT
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


def list_files(raw):
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
                    allowed(rel)
                    and not p.is_symlink()
                    and p.resolve().is_relative_to(root)
                    and p.stat().st_size <= 200000
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
