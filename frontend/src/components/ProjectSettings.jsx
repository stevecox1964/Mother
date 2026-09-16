import { useState } from "react";
import {
  ArrowRight,
  Check,
  Code2,
  FolderOpen,
  Users,
  Search,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { IconButton, Field, Dialog } from "./ui";

export function ProjectSettings({ settings, setSettings, fail, api, project }) {
  const [document, setDocument] = useState(null);
  const [path, setPath] = useState(settings.project_path),
    [files, setFiles] = useState([]),
    [selected, setSelected] = useState(settings.context_files),
    [filter, setFilter] = useState(""),
    [cap, setCap] = useState(settings.max_context_chars),
    [status, setStatus] = useState(""),
    [busy, setBusy] = useState(false);
  const load = async () => {
    setBusy(true);
    try {
      const r = await api("/workspace/files", "POST", { path });
      setFiles(r.files);
      setStatus(
        r.truncated
          ? "Showing a bounded file list. Narrow the project folder to see more files."
          : r.files.length + " source files found.",
      );
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="settings-page">
      <div className="page-heading">
        <div>
          <h1>Project folder & context</h1>
          <p>
            Set this project's folder and select source files to include in
            conversations.
          </p>
        </div>
        <button
          className="primary"
          onClick={async () => {
            try {
              setSettings(
                await api("/settings", "PUT", {
                  ...settings,
                  project_path: path,
                  context_files: selected,
                  max_context_chars: cap,
                }),
              );
              setStatus("Project setup saved.");
            } catch (e) {
              fail(e);
            }
          }}
        >
          <Check size={16} />
          Save context
        </button>
      </div>
      <div className="project-body">
        <div className="project-storage">
          <strong>
            {project.name} · {project.is_main ? "Main project" : project.type}
          </strong>
          <span>Project storage</span>
          <code>{project.storage_path}</code>
          <p>
            Conversations are saved automatically. Model profiles and selected
            context belong to this project.
          </p>
          {project.is_main && (
            <div className="mother-documents">
              <h3>Mother system development</h3>
              <p>
                Architecture, development plans and updates to Mother belong
                here. This project uses Mother's source repository and its own
                conversation stack.
              </p>
              {project.documents.map((doc) => (
                <button
                  key={doc.id}
                  className="secondary"
                  onClick={async () => {
                    try {
                      setDocument(
                        await api(
                          `/projects/${project.id}/documents/${doc.id}`,
                        ),
                      );
                    } catch (e) {
                      fail(e);
                    }
                  }}
                >
                  <Code2 size={16} />
                  {doc.title}
                  <ArrowRight size={15} />
                </button>
              ))}
              <small>
                These documents are selected as model context when the Mother
                project is created. File access remains configurable in Models &
                souls.
              </small>
            </div>
          )}
        </div>
        {document && (
          <Dialog label={document.title} onClose={() => setDocument(null)}>
            <div className="modal-heading">
              <h2>{document.title}</h2>
              <IconButton
                title="Close document"
                onClick={() => setDocument(null)}
              >
                <X size={18} />
              </IconButton>
            </div>
            <div className="project-document">
              <ReactMarkdown>{document.content}</ReactMarkdown>
            </div>
          </Dialog>
        )}
        <div className="project-intro">
          <Code2 size={26} />
          <div>
            <h3>One project, different levels of context.</h3>
            <p>
              Selected files go to models with code access on the next message.
              Board-only models learn from their peers. This version reads
              source files and proposes changes. Shared /tools and /docs folders
              are configured separately in System setup.
            </p>
          </div>
        </div>
        <div className="path-row">
          <Field label="Project folder on this machine">
            <input
              value={path}
              onChange={(e) => {
                setPath(e.target.value);
                setFiles([]);
                setSelected([]);
              }}
              placeholder="C:\Users\user\Desktop\MyProject"
            />
          </Field>
          <button className="secondary" onClick={load} disabled={busy}>
            <FolderOpen size={16} />
            {busy ? "Reading…" : "Browse files"}
          </button>
        </div>
        <div className="file-toolbar">
          <div className="search-input">
            <Search size={16} />
            <input
              placeholder="Filter source files…"
              aria-label="Filter files"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <span>{selected.length} selected</span>
          <button className="subtle-link" onClick={() => setSelected([])}>
            Clear selection
          </button>
        </div>
        <div className="file-list">
          {files.length ? (
            files
              .filter((f) =>
                f.path.toLowerCase().includes(filter.toLowerCase()),
              )
              .map((f) => (
                <label key={f.path}>
                  <input
                    type="checkbox"
                    checked={selected.includes(f.path)}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selected, f.path]
                          : selected.filter((p) => p !== f.path),
                      )
                    }
                  />
                  <Code2 size={14} />
                  <code>{f.path}</code>
                  <small>{(f.bytes / 1024).toFixed(1)} KB</small>
                </label>
              ))
          ) : (
            <p>
              {selected.length
                ? `${selected.length} saved files selected. Browse the folder to review the selection.`
                : "Enter a project folder, then browse its source files."}
            </p>
          )}
        </div>
        <div className="context-limit">
          <Field label="Maximum source context (characters)">
            <input
              type="number"
              min={1000}
              max={200000}
              step={1000}
              value={cap}
              onChange={(e) => setCap(Number(e.target.value))}
            />
          </Field>
          <p>
            Dependency folders, common credential files, and binary files are
            excluded. Each run records the selected file paths and content
            hashes.
          </p>
        </div>
        {status && (
          <p className="success-text" role="status">
            {status}
          </p>
        )}
      </div>
    </div>
  );
}
