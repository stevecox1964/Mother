import base64
import binascii
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.exceptions import HTTPException
from .store import Store, uid, now as store_now
from .config import Config
from .ensemble import Ensemble
from .search import SearchService
from . import workspace
from .file_tools import WRITE_LOCK
from .model_tools import list_models
from .providers import ProviderError
from .projects import Projects, PROJECT_TYPES, MOTHER_PROJECT_ID
from .mentions import recipient
from .notebook import Notebook, recent_images, remove_images


def create_app(data_dir=None, start_search_worker=False):
    # Single Flask API + built React SPA, adapted from BookMarkManager.
    root = Path(__file__).resolve().parents[2]
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
    store = Store(data_dir or os.environ.get("MOTHER_DATA_DIR", root / "data"))
    config = Config(store.root)
    projects = Projects(store, config, root)
    ensemble = Ensemble(store, config)
    search_service = SearchService(store)
    notebook = Notebook(store)
    store.on_search_change = search_service.wake
    app.extensions.update(
        store=store, mother_config=config, ensemble=ensemble, search=search_service,
        projects=projects, notebook=notebook,
    )
    if start_search_worker:
        search_service.start()

    @app.before_request
    def local_only():
        hostname = urlparse("http://" + request.host).hostname
        if hostname not in ("127.0.0.1", "localhost", "::1"):
            return jsonify(error="Mother accepts localhost requests only."), 403
        origin = request.headers.get("Origin")
        if origin and origin not in (
            request.host_url.rstrip("/"),
            "http://127.0.0.1:5174",
            "http://localhost:5174",
        ):
            return jsonify(error="Cross-origin request rejected."), 403
        if request.method in ("POST", "PUT", "DELETE") and not request.is_json:
            return jsonify(error="Use application/json."), 415

    @app.errorhandler(Exception)
    def errors(exc):
        if isinstance(exc, HTTPException):
            return jsonify(error=exc.description), exc.code
        if isinstance(exc, (ValueError, TypeError, KeyError)):
            return jsonify(error=str(exc)), 400
        if isinstance(exc, ProviderError):
            return jsonify(error=str(exc)), 502
        if isinstance(exc, sqlite3.IntegrityError):
            return jsonify(
                error="A discussion is already running in this conversation."
            ), 409
        app.logger.exception("Request failed")
        return jsonify(error="Internal error. See the server log."), 500

    def body():
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")
        return data

    def require_conversation(cid):
        if not store.exists(cid):
            from flask import abort

            abort(404, description="Conversation not found.")
        require_scope(cid)

    def project_id():
        pid = request.args.get("project_id", "default")
        if not store.project(pid):
            from flask import abort
            abort(404, description="Project not found.")
        return pid

    def require_scope(cid):
        if "project_id" in request.args and store.conversation_project(cid) != project_id():
            from flask import abort
            abort(404, description="Conversation not found in this project.")

    def selected_config():
        return projects.config(project_id())

    def public_settings():
        return {**selected_config().public(projects.read(project_id())), "project_id": project_id()}

    @app.get("/api/system/settings")
    def system_settings_get():
        return jsonify(projects.system.config.public())

    @app.put("/api/system/settings")
    def system_settings_put():
        data = body()
        shared = data.get("shared_paths", {})
        if not isinstance(shared, dict) or any(not isinstance(v, str) for v in shared.values()):
            raise ValueError("Shared folders must contain tools and docs paths.")
        for path in shared.values():
            if path:
                workspace.root_path(path)
        projects.system.save_system(data)
        return jsonify(projects.system.config.public())

    @app.get("/api/system/providers/<provider>/models")
    def system_provider_models(provider):
        return jsonify(list_models(projects.system.config, provider, request.args.get("profile_id")))

    @app.get("/api/projects")
    def projects_get():
        rows = sorted(store.projects(), key=lambda p: p["id"] != MOTHER_PROJECT_ID)
        return jsonify(projects=[projects.public(p) for p in rows], types=PROJECT_TYPES,
                       default_project_id=MOTHER_PROJECT_ID)

    @app.get("/api/projects/<pid>/documents/<key>")
    def project_document(pid, key):
        if pid != project_id():
            return jsonify(error="Document not found in this project."), 404
        return jsonify(projects.document(pid, key))

    # Browsing and uploads for the Files page. Images and PDFs are listed here only.
    @app.get("/api/files")
    def project_files():
        return jsonify(workspace.list_files(projects.read(project_id())["project_path"], media=True))

    @app.get("/api/files/raw")
    def project_file_raw():
        rel = request.args.get("path", "")
        _, path = workspace.project_file(projects.read(project_id())["project_path"], rel, media=True)
        mime = workspace.MEDIA.get(path.suffix.lower())
        if not mime or not path.is_file() or path.stat().st_size > workspace.MAX_MEDIA_BYTES:
            raise ValueError(f"Not an image or PDF in this project: {rel}")
        response = send_file(path, mimetype=mime)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/api/files/upload")
    def project_file_upload():
        data = body()
        try:
            raw = base64.b64decode(data["base64"], validate=True)
        except (binascii.Error, KeyError, TypeError):
            raise ValueError("Invalid file data.")
        with WRITE_LOCK:
            saved = workspace.save_upload(projects.read(project_id())["project_path"],
                                          data.get("path"), raw, Path(config.root) / "backups")
        return jsonify(saved), 201

    @app.get("/api/files/content")
    def project_file_content():
        rel = request.args.get("path", "")
        _, manifest = workspace.snapshot(
            {"project_path": projects.read(project_id())["project_path"],
             "context_files": [rel], "max_context_chars": 400000},
            include_bodies=True,
        )
        return jsonify(path=rel, content=manifest[0]["body"], bytes=manifest[0]["bytes"])

    @app.post("/api/projects")
    def projects_post():
        return jsonify(projects.create(body(), project_id())), 201

    @app.put("/api/projects/<pid>")
    def projects_put(pid):
        if not store.project(pid):
            return jsonify(error="Project not found."), 404
        return jsonify(projects.update(pid, body()))

    @app.delete("/api/projects/<pid>")
    def projects_delete(pid):
        if not projects.delete(pid):
            return jsonify(error="Project not found."), 404
        return jsonify(deleted=True)

    @app.get("/api/projects/deleted")
    def projects_deleted():
        return jsonify(store.deleted_projects())

    @app.post("/api/projects/<pid>/restore")
    def projects_restore(pid):
        project = projects.restore(pid)
        if not project:
            return jsonify(error="Project not found in deleted projects."), 404
        return jsonify(project)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", name="Mother", version="0.1.0")

    @app.get("/api/settings")
    def settings_get():
        return jsonify(public_settings())

    @app.get("/api/providers/<provider>/models")
    def provider_models(provider):
        return jsonify(list_models(selected_config(), provider, request.args.get("profile_id"), settings=projects.read(project_id())))

    @app.put("/api/settings")
    def settings_put():
        projects.system.save_project(project_id(), body())
        return jsonify(public_settings())

    @app.put("/api/credentials")
    def credentials():
        data = body()
        config.save_key(data.get("name", ""), data.get("value", ""))
        return jsonify(saved=True)

    @app.post("/api/workspace/files")
    def files():
        return jsonify(workspace.list_files(str(body().get("path", ""))))

    @app.get("/api/conversations")
    def conversations():
        return jsonify(store.conversations(project_id()))

    @app.post("/api/conversations")
    def create_conversation():
        return jsonify(
            store.create_conversation(str(body().get("title", "New conversation")), project_id())
        ), 201

    @app.get("/api/conversations/<cid>")
    def conversation(cid):
        require_conversation(cid)
        after = max(0, int(request.args.get("after", 0)))
        return jsonify(
            events=store.events(cid, after),
            runs=store.runs(cid),
            participation=store.participation(cid),
            cells=store.cells(cid),
        )

    # Code cells. Code runs only on the user's click, in the project folder.
    def media_folder(cid):
        pid = store.conversation_project(cid)
        return (store.root if pid == "default" else store.project_folder(pid)) / "attachments"

    def kernel_folder(cid):
        path = Path(projects.read(store.conversation_project(cid)).get("project_path") or "")
        return path if str(path) and path.is_dir() else media_folder(cid).parent

    def require_cell(cell_id):
        cell = store.cell(cell_id)
        if not cell:
            return None
        require_conversation(cell["conversation_id"])
        return cell

    def cell_source(data, default=None):
        source = data.get("source", default)
        if not isinstance(source, str) or len(source) > 100000:
            raise ValueError("Cell code must be text up to 100,000 characters.")
        return source

    @app.post("/api/conversations/<cid>/cells")
    def cell_create(cid):
        require_conversation(cid)
        return jsonify(store.add_cell(cid, cell_source(body(), ""))), 201

    @app.put("/api/cells/<cell_id>")
    def cell_update(cell_id):
        if not require_cell(cell_id):
            return jsonify(error="Cell not found."), 404
        data = body()
        fields = {}
        if "source" in data:
            fields["source"] = cell_source(data)
        if "collapsed" in data:
            if type(data["collapsed"]) is not bool:
                raise ValueError("collapsed must be true or false.")
            fields["collapsed"] = data["collapsed"]
        store.update_cell(cell_id, **fields)
        return jsonify(store.cell(cell_id))

    @app.delete("/api/cells/<cell_id>")
    def cell_delete(cell_id):
        cell = require_cell(cell_id)
        if not cell:
            return jsonify(error="Cell not found."), 404
        if cell["status"] in ("queued", "running"):
            raise ValueError("Stop the code before deleting this cell.")
        store.update_cell(cell_id, deleted_at=store_now())
        remove_images(media_folder(cell["conversation_id"]), cell["outputs"])
        return jsonify(deleted=True)

    @app.post("/api/cells/<cell_id>/run")
    def cell_run(cell_id):
        cell = require_cell(cell_id)
        if not cell:
            return jsonify(error="Cell not found."), 404
        if cell["status"] in ("queued", "running"):
            raise ValueError("This cell is already running.")
        store.update_cell(cell_id, source=cell_source(body(), cell["source"]))
        cid = cell["conversation_id"]
        notebook.run(cid, cell_id, kernel_folder(cid), media_folder(cid))
        return jsonify(store.cell(cell_id)), 202

    @app.post("/api/conversations/<cid>/cells/run-all")
    def cells_run_all(cid):
        require_conversation(cid)
        if any(c["status"] in ("queued", "running") for c in store.cells(cid)):
            raise ValueError("Code is already running. Stop it first.")
        notebook.run_all(cid, kernel_folder(cid), media_folder(cid))
        return jsonify(cells=store.cells(cid)), 202

    @app.post("/api/conversations/<cid>/cells/stop")
    def cells_stop(cid):
        require_conversation(cid)
        notebook.interrupt(cid)
        return jsonify(stopped=True)

    @app.put("/api/conversations/<cid>/models/<mid>/squelch")
    def squelch(cid, mid):
        require_conversation(cid)
        value = body().get("squelched")
        if type(value) is not bool:
            raise ValueError("squelched must be true or false.")
        if mid not in [p["id"] for p in projects.config(store.conversation_project(cid)).read()["models"]]:
            raise ValueError("Unknown model profile.")
        return jsonify(
            participation=store.set_squelch(cid, mid, value), runs=store.runs(cid)
        )

    @app.put("/api/conversations/<cid>")
    def rename_conversation(cid):
        require_conversation(cid)
        title = body().get("title")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 160:
            raise ValueError("Conversation name must contain 1–160 characters.")
        if not store.rename_conversation(cid, title.strip()):
            return jsonify(error="Conversation not found."), 404
        return jsonify(id=cid, title=title.strip())

    @app.delete("/api/conversations/<cid>")
    def delete_conversation(cid):
        require_conversation(cid)
        if not store.delete_conversation(cid):
            return jsonify(error="Conversation not found."), 404
        return jsonify(deleted=True)

    @app.get("/api/trash")
    def trash():
        return jsonify(store.deleted_conversations(project_id()))

    @app.post("/api/conversations/<cid>/restore")
    def restore_conversation(cid):
        require_scope(cid)
        if not store.restore_conversation(cid):
            return jsonify(error="Deleted conversation not found."), 404
        return jsonify(restored=True)

    @app.get("/api/conversations/<cid>/export")
    def export(cid):
        require_conversation(cid)
        content = "".join(
            json.dumps(e, ensure_ascii=False) + "\n" for e in store.events(cid)
        )
        return app.response_class(
            content,
            mimetype="application/x-ndjson",
            headers={
                "Content-Disposition": f'attachment; filename="mother-{cid}.jsonl"'
            },
        )

    @app.get("/api/search")
    def search():
        return jsonify(
            store.search(
                request.args.get("q", ""),
                request.args.get("start", ""),
                request.args.get("end", ""),
                request.args.get("conversation_id", ""),
                project_id(),
            )
        )

    @app.get("/api/search/hybrid")
    def hybrid_search():
        from datetime import date

        start, end = request.args.get("start", ""), request.args.get("end", "")
        for value in (start, end):
            if value:
                date.fromisoformat(value)
        if start and end and start > end:
            raise ValueError("The start date must be before the end date.")
        return jsonify(
            search_service.search(
                request.args.get("q", ""),
                start,
                end,
                request.args.get("conversation_id", ""),
                request.args.get("mode", "hybrid"),
                project_id(),
            )
        )

    @app.get("/api/search/status")
    def search_status():
        return jsonify(search_service.status(project_id()))

    @app.post("/api/search/index")
    def index_search():
        pid = project_id()
        search_service.retry()
        return jsonify(search_service.status(pid)), 202

    @app.post("/api/conversations/<cid>/messages")
    def message(cid):
        require_conversation(cid)
        data = body()
        content = str(data.get("content", "")).strip()
        if not content or len(content) > 40000:
            raise ValueError("Message must contain 1–40,000 characters.")
        settings = projects.read(store.conversation_project(cid))
        mode = data.get("mode", "direct")
        if mode not in ("direct", "broadcast", "opinions"):
            raise ValueError("Choose direct, broadcast or opinions mode.")
        rounds = data.get("rounds", 2) if mode != "direct" else 1
        if type(rounds) is not int or not 1 <= rounds <= 3:
            raise ValueError("Use 1–3 discussion rounds.")
        targets = data.get("targets", [])
        mentioned = recipient(content, settings["models"])
        if mentioned:
            mode, rounds, targets = "direct", 1, [mentioned]
        if not isinstance(targets, list) or any(
            not isinstance(t, str) for t in targets
        ):
            raise ValueError("Invalid targets.")
        active = [p for p in settings["models"] if p["enabled"]]
        if any(t not in [p["id"] for p in active] for t in targets):
            raise ValueError("Target model is missing or disabled.")
        if mode == "direct" and len(targets) > 1:
            raise ValueError("Choose one model per message.")
        if not active:
            raise ValueError("Enable a model in Models & souls first.")
        if mode == "direct" and not targets:
            default = next(
                (p for p in active if p["id"] == settings["chief_id"]), active[0]
            )
            targets = [default["id"]]
        selected = [
            p
            for p in active
            if (not targets or p["id"] in targets)
            and not store.voice(cid, p["id"])["squelched"]
        ]
        if not selected:
            raise ValueError(
                "All selected models are squelched. Unsquelch a participant first."
            )
        targets = [p["id"] for p in selected]
        unavailable = [
            p["name"]
            for p in selected
            if not p["model"] or (p["api_key_env"] and not config.key(p))
        ]
        if unavailable:
            raise ValueError(
                "Configure credentials and model IDs for: " + ", ".join(unavailable)
            )
        code, manifest = workspace.model_snapshots(settings, selected)
        images = []
        attachments = data.get("images", [])
        if not isinstance(attachments, list) or len(attachments) > 2:
            raise ValueError("Attach up to two images.")
        if attachments and not any(p["vision"] for p in selected):
            raise ValueError("Enable image input on at least one selected model.")
        for im in attachments:
            try:
                raw = base64.b64decode(im["base64"], validate=True)
            except (binascii.Error, KeyError, TypeError):
                raise ValueError("Invalid image data.")
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError("Images must be smaller than 4 MB each.")
            mime = (
                "image/png"
                if raw.startswith(b"\x89PNG\r\n\x1a\n")
                else "image/jpeg"
                if raw.startswith(b"\xff\xd8\xff")
                else "image/webp"
                if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"
                else ""
            )
            if not mime:
                raise ValueError("Use PNG, JPEG or WebP images.")
            images.append(
                dict(
                    id=uid(),
                    name=str(im.get("name", "image"))[:200],
                    mime=mime,
                    base64=im["base64"],
                    data_url=f"data:{mime};base64," + im["base64"],
                )
            )
        # Images from code cells since the last user message go to vision models.
        cell_images = recent_images(store, cid, media_folder(cid)) if any(p["vision"] for p in selected) else []
        run = store.start_run(cid, mode, rounds, targets)
        try:
            pid = store.conversation_project(cid)
            folder = (store.root if pid == "default" else store.project_folder(pid)) / "attachments"
            folder.mkdir(exist_ok=True)
            for im in images:
                (folder / im["id"]).write_bytes(base64.b64decode(im["base64"]))
            meta = [{k: im[k] for k in ("id", "name", "mime")} for im in images]
            store.add(
                cid,
                "user",
                "You",
                content,
                {
                    "run_id": run["id"],
                    "targets": targets,
                    "images": meta,
                    "mode": mode,
                    "rounds": rounds,
                },
            )
            ensemble.launch(run, settings, targets, code, manifest, images + cell_images)
        except Exception:
            store.finish(run["id"], "failed")
            raise
        return jsonify(run), 202

    @app.get("/api/attachments/<aid>")
    def attachment(aid):
        import re

        if not re.fullmatch("[a-f0-9]{32}", aid):
            raise ValueError("Invalid attachment ID.")
        # IDs are globally unique; retain old attachment URLs in saved transcripts.
        folder = store.root / "attachments"
        if not (folder / aid).is_file():
            for project in store.projects():
                candidate = store.project_folder(project["id"]) / "attachments"
                if (candidate / aid).is_file():
                    folder = candidate
                    break
        return send_from_directory(
            folder, aid, mimetype="application/octet-stream"
        )

    @app.post("/api/runs/<rid>/cancel")
    def cancel(rid):
        run = store.run(rid)
        if not run:
            return jsonify(error="Run not found."), 404
        require_scope(run["conversation_id"])
        store.finish(rid, "cancelled")
        if run["status"] == "running":
            store.add(
                run["conversation_id"],
                "system",
                "Mother",
                "Stopped. In-flight provider requests may finish, but their output will be discarded.",
                {"run_id": rid},
            )
        return jsonify(store.run(rid))

    @app.get("/")
    @app.get("/<path:path>")
    def spa(path=""):
        if path.startswith("api/"):
            return jsonify(error="Endpoint not found."), 404
        dist = root / "frontend" / "dist"
        if not (dist / "index.html").exists():
            return "Run npm install and npm run build in frontend first.", 503
        return send_from_directory(
            dist, path if path and (dist / path).is_file() else "index.html"
        )

    return app
