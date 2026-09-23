import time
from pathlib import Path

import pytest

from mother.app import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path / "data")
    cfg = app.extensions["mother_config"]
    settings = cfg.read()
    settings["models"] = [cfg.profile("chief", "Chief", "demo", "simulated", "Be clear")]
    cfg.save(settings)
    yield app
    app.extensions["notebook"].shutdown()


def wait_cells(client, cid, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        cells = client.get(f"/api/conversations/{cid}").json["cells"]
        if all(c["status"] not in ("queued", "running") for c in cells):
            return cells
        time.sleep(0.1)
    raise AssertionError("cells did not finish")


def add_cell(client, cid, source):
    response = client.post(f"/api/conversations/{cid}/cells", json={"source": source})
    assert response.status_code == 201
    return response.json["id"]


def test_cells_keep_state_show_images_and_sit_between_chat(app):
    c = app.test_client()
    store = app.extensions["store"]
    cid = c.post("/api/conversations", json={"title": "Plots"}).json["id"]
    store.add(cid, "user", "You", "Make a chart")
    first = add_cell(c, cid, "x = 21\nprint('hello')")
    second = add_cell(
        c, cid,
        "import matplotlib.pyplot as plt\nplt.plot([1, 2, 3])\nplt.show()\nx * 2",
    )
    assert c.post(f"/api/cells/{first}/run", json={}).status_code == 202
    wait_cells(c, cid)
    assert c.post(f"/api/cells/{second}/run", json={}).status_code == 202
    one, two = wait_cells(c, cid)
    assert one["status"] == "ok" and one["outputs"] == [{"type": "stream", "name": "stdout", "text": "hello\n"}]
    assert two["status"] == "ok"
    image = next(o for o in two["outputs"] if o["type"] == "image")
    assert c.get("/api/attachments/" + image["id"]).data.startswith(b"\x89PNG")
    assert {"type": "text", "text": "42"} in two["outputs"]  # state kept between cells
    # Cells appear in the timeline after the chat message, and models read their output.
    kinds = [e["kind"] for e in c.get(f"/api/conversations/{cid}").json["events"]]
    assert kinds == ["user", "cell", "cell"]
    history = app.extensions["ensemble"].history(cid)
    assert history.index("Make a chart") < history.index("x = 21") < history.index("hello")
    assert "42" in history and "[Image output]" in history
    from mother.notebook import recent_images
    media = Path(store.root) / "attachments"
    assert [im["id"] for im in recent_images(store, cid, media)] == [image["id"]]
    store.add(cid, "user", "You", "Thanks")
    assert recent_images(store, cid, media) == []
    # Deleting a cell hides it from the timeline data, from models and removes its image.
    assert c.delete(f"/api/cells/{second}", json={}).status_code == 200
    assert [x["id"] for x in c.get(f"/api/conversations/{cid}").json["cells"]] == [first]
    assert "x * 2" not in app.extensions["ensemble"].history(cid)
    assert not (media / image["id"]).exists()


def test_run_all_restarts_runs_in_order_and_stops_at_first_error(app):
    c = app.test_client()
    cid = c.post("/api/conversations", json={"title": "Order"}).json["id"]
    a = add_cell(c, cid, "stale = 1")
    c.post(f"/api/cells/{a}/run", json={})
    wait_cells(c, cid)
    c.put(f"/api/cells/{a}", json={"source": "fresh = 1\nprint('a')"})
    b = add_cell(c, cid, "print('b', 'stale' in dir())")
    d = add_cell(c, cid, "raise ValueError('boom')")
    e = add_cell(c, cid, "print('never')")
    assert c.post(f"/api/conversations/{cid}/cells/run-all", json={}).status_code == 202
    cells = {x["id"]: x for x in wait_cells(c, cid)}
    assert cells[a]["outputs"][0]["text"] == "a\n"
    # A fresh kernel: the old variable is gone.
    assert cells[b]["outputs"][0]["text"] == "b False\n"
    assert cells[d]["status"] == "error" and cells[d]["outputs"][0]["evalue"] == "boom"
    assert cells[e]["status"] == "skipped" and cells[e]["outputs"] == []
    assert [cells[x]["execution_count"] for x in (a, b, d)] == [1, 2, 3]


def test_stop_interrupts_running_code_and_collapse_persists(app):
    c = app.test_client()
    cid = c.post("/api/conversations", json={"title": "Stop"}).json["id"]
    cell = add_cell(c, cid, "import time\ntime.sleep(60)")
    c.post(f"/api/cells/{cell}/run", json={})
    deadline = time.monotonic() + 30
    while c.get(f"/api/conversations/{cid}").json["cells"][0]["status"] != "running":
        assert time.monotonic() < deadline
        time.sleep(0.1)
    assert c.post(f"/api/cells/{cell}/run", json={}).status_code == 400
    time.sleep(0.5)
    started = time.monotonic()
    c.post(f"/api/conversations/{cid}/cells/stop", json={})
    [done] = wait_cells(c, cid, timeout=20)
    assert time.monotonic() - started < 20
    # Windows cannot interrupt time.sleep, so Mother kills the kernel after a short wait.
    assert done["status"] == "error" and done["outputs"][-1]["ename"] in ("KeyboardInterrupt", "RuntimeError")
    busy = add_cell(c, cid, "while True:\n    pass")
    c.post(f"/api/cells/{busy}/run", json={})
    time.sleep(3)
    c.post(f"/api/conversations/{cid}/cells/stop", json={})
    assert wait_cells(c, cid, timeout=20)[1]["outputs"][-1]["ename"] == "KeyboardInterrupt"
    assert c.put(f"/api/cells/{cell}", json={"collapsed": True}).json["collapsed"] is True
    assert c.get(f"/api/conversations/{cid}").json["cells"][0]["collapsed"] is True
