"""Code cells: one Jupyter kernel per conversation, run only on the user's click."""

import atexit
import base64
import logging
import re
import threading
from pathlib import Path

from .store import uid

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
MAX_TEXT = 100_000
IMAGE_MIMES = {"image/png": ".png", "image/jpeg": ".jpg"}


class Notebook:
    def __init__(self, store):
        self.store = store
        self.kernels = {}  # cid -> (manager, client)
        self.locks = {}  # cid -> lock; a kernel runs one cell at a time
        self.cancelled = set()
        self.running = {}  # cid -> cell id
        self.guard = threading.Lock()
        atexit.register(self.shutdown)

    def lock(self, cid):
        with self.guard:
            return self.locks.setdefault(cid, threading.Lock())

    def kernel(self, cid, cwd):
        pair = self.kernels.get(cid)
        if pair and pair[0].is_alive():
            return pair
        from jupyter_client.manager import KernelManager

        manager = KernelManager(kernel_name="python3")
        manager.start_kernel(cwd=str(cwd))
        client = manager.blocking_client()
        client.start_channels()
        client.wait_for_ready(timeout=60)
        self.kernels[cid] = (manager, client)
        return manager, client

    def stop_kernel(self, cid):
        pair = self.kernels.pop(cid, None)
        if pair:
            pair[1].stop_channels()
            pair[0].shutdown_kernel(now=True)

    def shutdown(self):
        for cid in list(self.kernels):
            try:
                self.stop_kernel(cid)
            except Exception:
                pass

    def interrupt(self, cid, grace=5):
        self.cancelled.add(cid)
        pair, cell_id = self.kernels.get(cid), self.running.get(cid)
        if not pair or not cell_id:
            return
        pair[0].interrupt_kernel()

        # Windows cannot interrupt some calls (time.sleep, blocking I/O). Kill the kernel instead.
        def force():
            if self.running.get(cid) == cell_id and pair[0].is_alive():
                pair[0].shutdown_kernel(now=True)

        threading.Timer(grace, force).start()

    def run(self, cid, cell_id, cwd, media):
        self.cancelled.discard(cid)
        self.store.update_cell(cell_id, status="queued")
        threading.Thread(
            target=self._run_one, args=(cid, cell_id, cwd, media), daemon=True
        ).start()

    def run_all(self, cid, cwd, media):
        self.cancelled.discard(cid)
        cells = self.store.cells(cid)
        for cell in cells:
            self.store.update_cell(cell["id"], status="queued")
        threading.Thread(
            target=self._run_all, args=(cid, [c["id"] for c in cells], cwd, media), daemon=True
        ).start()

    def _run_one(self, cid, cell_id, cwd, media):
        with self.lock(cid):
            if cid in self.cancelled:
                self.store.update_cell(cell_id, status="cancelled")
                return
            self.execute(cid, cell_id, cwd, media)

    def _run_all(self, cid, ids, cwd, media):
        with self.lock(cid):
            self.stop_kernel(cid)  # fresh kernel: top-to-bottom from a clean state
            for n, cell_id in enumerate(ids):
                if cid in self.cancelled:
                    rest = ids[n:]
                elif not self.execute(cid, cell_id, cwd, media):
                    rest = ids[n + 1:]
                else:
                    continue
                for skipped in rest:
                    self.store.update_cell(skipped, status="skipped")
                return

    def execute(self, cid, cell_id, cwd, media):
        """Run one cell and save its outputs. Returns True when it finished without error."""
        cell = self.store.cell(cell_id)
        if not cell:
            return True
        old = cell["outputs"]
        outputs, count, ok = [], None, True
        self.running[cid] = cell_id
        try:
            manager, client = self.kernel(cid, cwd)
            if cid in self.cancelled:  # Stop was pressed while the kernel started
                self.store.update_cell(cell_id, status="cancelled")
                return False
            self.store.update_cell(cell_id, status="running", outputs=[])
            msg_id = client.execute(cell["source"], allow_stdin=False)
            while True:
                try:
                    msg = client.get_iopub_msg(timeout=1)
                except Exception:  # queue.Empty: check the kernel is still alive
                    if not manager.is_alive():
                        if self.kernels.get(cid, (None,))[0] is manager:
                            self.kernels.pop(cid)
                        client.stop_channels()
                        raise RuntimeError("The kernel stopped, so all variables are cleared. Run the cells again.")
                    continue
                if msg["parent_header"].get("msg_id") != msg_id:
                    continue
                kind, content = msg["msg_type"], msg["content"]
                if kind == "status" and content["execution_state"] == "idle":
                    break
                if kind == "stream":
                    if outputs and outputs[-1]["type"] == "stream" and outputs[-1]["name"] == content["name"]:
                        outputs[-1]["text"] = (outputs[-1]["text"] + content["text"])[-MAX_TEXT:]
                    else:
                        outputs.append({"type": "stream", "name": content["name"], "text": content["text"][-MAX_TEXT:]})
                elif kind in ("execute_result", "display_data"):
                    data = content["data"]
                    mime = next((m for m in IMAGE_MIMES if m in data), None)
                    if mime:
                        image_id = uid()
                        media.mkdir(parents=True, exist_ok=True)
                        (media / image_id).write_bytes(base64.b64decode(data[mime]))
                        outputs.append({"type": "image", "id": image_id, "mime": mime})
                    elif "text/plain" in data:
                        outputs.append({"type": "text", "text": data["text/plain"][:MAX_TEXT]})
                    if kind == "execute_result":
                        count = content.get("execution_count")
                elif kind == "execute_input":
                    count = content.get("execution_count")
                elif kind == "error":
                    ok = False
                    outputs.append({
                        "type": "error",
                        "ename": content["ename"],
                        "evalue": content["evalue"],
                        "traceback": ANSI.sub("", "\n".join(content["traceback"]))[-MAX_TEXT:],
                    })
                self.store.update_cell(cell_id, outputs=outputs)
        except Exception as exc:
            logging.getLogger(__name__).exception("Cell run failed")
            ok = False
            outputs.append({"type": "error", "ename": type(exc).__name__, "evalue": str(exc), "traceback": ""})
        finally:
            self.running.pop(cid, None)
        self.store.update_cell(
            cell_id, outputs=outputs, execution_count=count, status="ok" if ok else "error"
        )
        remove_images(media, old)
        return ok


def remove_images(media, outputs):
    for out in outputs:
        if out.get("type") == "image":
            Path(media, out["id"]).unlink(missing_ok=True)


def history_text(cell):
    """How a cell reads in model context: code plus text outputs, images noted."""
    lines = [f"```python\n{cell['source']}\n```"]
    if cell["status"] in ("new", "queued", "skipped", "cancelled"):
        lines.append(f"(Not run: {cell['status']}.)")
    for out in cell["outputs"]:
        if out["type"] in ("stream", "text"):
            lines.append("Output:\n" + out["text"][-4000:])
        elif out["type"] == "image":
            lines.append("[Image output]")
        elif out["type"] == "error":
            lines.append(f"Error: {out['ename']}: {out['evalue']}")
    return "\n".join(lines)


def recent_images(store, cid, media, limit=2):
    """Latest image outputs from cells after the last user message, for vision models."""
    events = store.events(cid)
    last_user = max((e["seq"] for e in events if e["kind"] == "user"), default=0)
    found = []
    for e in events:
        if e["kind"] == "cell" and e["seq"] > last_user:
            cell = store.cell(e["metadata"]["cell_id"])
            for out in (cell or {}).get("outputs", []):
                path = Path(media, out.get("id", ""))
                if out["type"] == "image" and path.is_file():
                    data = base64.b64encode(path.read_bytes()).decode()
                    found.append({"id": out["id"], "name": "cell output", "mime": out["mime"],
                                  "base64": data, "data_url": f"data:{out['mime']};base64,{data}"})
    return found[-limit:]
