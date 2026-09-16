import { useEffect, useRef } from "react";

export const names = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Google",
  ollama: "Local",
  compatible: "Compatible",
  demo: "Simulation",
};
export const time = (d) =>
  new Date(d).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
export const date = (d) =>
  new Date(d).toLocaleDateString([], { month: "short", day: "numeric" });
export const cx = (...s) => s.filter(Boolean).join(" ");
export function Avatar({ name, provider = "user", small = false }) {
  return (
    <span className={cx("avatar", provider, small && "small")}>
      {name?.slice(0, 1).toUpperCase() || "M"}
    </span>
  );
}
export function IconButton({ title, children, ...props }) {
  return (
    <button className="icon-button" title={title} aria-label={title} {...props}>
      {children}
    </button>
  );
}
export function Field({ label, children, hint }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

// Must match KNOWN_TOOLS in backend/mother/config.py.
export const TOOLS = [
  ["list_files", "List files"],
  ["read_file", "Read files"],
  ["search_files", "Search file text"],
  ["write_file", "Create and replace files"],
  ["edit_file", "Edit files"],
  ["get_model_settings", "Read Mother settings"],
  ["list_provider_models", "Look up provider models"],
  ["web_search", "Web search (Browserbase)"],
  ["web_fetch", "Read web pages (Browserbase)"],
];

// value null allows every tool; a list allows only the checked tools.
export function ToolChecklist({ value, onChange }) {
  const on = (name) => value == null || value.includes(name);
  return (
    <div className="tool-checklist">
      {TOOLS.map(([name, label]) => (
        <label className="checkbox" key={name}>
          <input
            type="checkbox"
            checked={on(name)}
            onChange={(e) => {
              const next = TOOLS.map(([n]) => n).filter((n) =>
                n === name ? e.target.checked : on(n),
              );
              onChange(next.length === TOOLS.length ? null : next);
            }}
          />
          {label} <code>{name}</code>
        </label>
      ))}
    </div>
  );
}

export function Dialog({ label, onClose, children }) {
  const ref = useRef();
  useEffect(() => {
    const previous = document.activeElement;
    (
      ref.current.querySelector("[autofocus], input, button") || ref.current
    ).focus();
    return () => {
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        ref={ref}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.stopPropagation();
            onClose();
          }
          if (e.key === "Tab") {
            const items = Array.from(
              ref.current.querySelectorAll(
                "button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href]",
              ),
            );
            const first = items[0],
              last = items[items.length - 1];
            if (!first) {
              e.preventDefault();
              return;
            }
            if (e.shiftKey && document.activeElement === first) {
              e.preventDefault();
              last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
              e.preventDefault();
              first.focus();
            }
          }
        }}
      >
        {children}
      </div>
    </div>
  );
}
