import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Play, Trash2 } from "lucide-react";
import { cx, IconButton } from "./ui";

const STATUS = {
  new: "Not run",
  queued: "Waiting…",
  running: "Running…",
  ok: "Done",
  error: "Error",
  skipped: "Skipped",
  cancelled: "Stopped",
};

// A code cell in the timeline. Code runs only when the user clicks Run.
export function Cell({ cell, api, fail, onChange }) {
  const [source, setSource] = useState(cell.source);
  const dirty = useRef(false);
  useEffect(() => {
    if (!dirty.current) setSource(cell.source);
  }, [cell.source]);
  const busy = cell.status === "queued" || cell.status === "running";
  const save = () => {
    if (!dirty.current) return;
    dirty.current = false;
    api(`/cells/${cell.id}`, "PUT", { source }).then(onChange).catch(fail);
  };
  const run = () => {
    dirty.current = false;
    api(`/cells/${cell.id}/run`, "POST", { source }).then(onChange).catch(fail);
  };
  const toggle = () =>
    api(`/cells/${cell.id}`, "PUT", { collapsed: !cell.collapsed })
      .then(onChange)
      .catch(fail);
  const remove = () =>
    api(`/cells/${cell.id}`, "DELETE", {})
      .then(() => onChange({ ...cell, deleted: true }))
      .catch(fail);
  const firstLine = source.split("\n").find((l) => l.trim()) || "Empty cell";
  return (
    <section
      className={cx("cell", "cell-" + cell.status)}
      aria-label="Code cell"
    >
      <div className="cell-head">
        <button
          className="cell-toggle"
          aria-expanded={!cell.collapsed}
          title={cell.collapsed ? "Open cell" : "Collapse cell"}
          onClick={toggle}
        >
          {cell.collapsed ? (
            <ChevronRight size={15} />
          ) : (
            <ChevronDown size={15} />
          )}
          <span className="cell-count">In [{cell.execution_count ?? " "}]</span>
          {cell.collapsed && <code>{firstLine}</code>}
        </button>
        <span className="cell-status">
          {STATUS[cell.status] || cell.status}
        </span>
        <IconButton
          title="Run cell (Shift+Enter)"
          disabled={busy}
          onClick={run}
        >
          <Play size={15} />
        </IconButton>
        <IconButton title="Delete cell" disabled={busy} onClick={remove}>
          <Trash2 size={15} />
        </IconButton>
      </div>
      {!cell.collapsed && (
        <>
          <textarea
            className="cell-source"
            aria-label="Cell code"
            spellCheck={false}
            placeholder="Python code. Shift+Enter to run."
            value={source}
            rows={Math.max(2, source.split("\n").length)}
            onChange={(e) => {
              dirty.current = true;
              setSource(e.target.value);
            }}
            onBlur={save}
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.shiftKey) {
                e.preventDefault();
                if (!busy) run();
              }
            }}
          />
          {cell.outputs.length > 0 && (
            <div className="cell-outputs">
              {cell.outputs.map((o, i) =>
                o.type === "image" ? (
                  <img
                    key={i}
                    src={"/api/attachments/" + o.id}
                    alt="Cell output"
                  />
                ) : o.type === "error" ? (
                  <pre key={i} className="cell-error">
                    {o.traceback || `${o.ename}: ${o.evalue}`}
                  </pre>
                ) : (
                  <pre
                    key={i}
                    className={o.name === "stderr" ? "cell-stderr" : undefined}
                  >
                    {o.text}
                  </pre>
                ),
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
