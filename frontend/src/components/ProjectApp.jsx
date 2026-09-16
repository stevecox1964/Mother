import { useEffect, useState } from "react";
import { ArrowRight, X } from "lucide-react";
import { api as globalApi, projectApi } from "../api";
import { IconButton, Field, Dialog } from "./ui";
import { App } from "./App";

export function ProjectApp() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(
    () =>
      localStorage.getItem("mother-active-project") ||
      (localStorage.getItem("mother-project") !== "default" &&
        localStorage.getItem("mother-project")) ||
      "mother",
  );
  const [types, setTypes] = useState([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null);
  const [name, setName] = useState("");
  const [type, setType] = useState("coding");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  useEffect(() => {
    globalApi("/projects")
      .then((data) => {
        setProjects(data.projects);
        setTypes(data.types);
        setProjectId((id) =>
          data.projects.some((p) => p.id === id) ? id : data.default_project_id,
        );
      })
      .catch((e) => setError(e.message));
  }, []);
  const select = (id) => {
    localStorage.setItem("mother-active-project", id);
    setProjectId(id);
  };
  const edit = (project = {}) => {
    setName(project.name || "");
    setType(project.type || "coding");
    setFormError("");
    setEditing(project);
  };
  const project = projects.find((p) => p.id === projectId);
  if (!project)
    return (
      <div className="loading">
        <h2>Opening Mother</h2>
        <p>{error || "Loading projects…"}</p>
        {error && <button onClick={() => location.reload()}>Retry</button>}
      </div>
    );
  return (
    <>
      <App
        key={projectId}
        project={project}
        projects={projects}
        selectProject={select}
        editProject={edit}
      />
      {editing && (
        <Dialog
          label={editing.id ? "Edit project" : "New project"}
          onClose={() => {
            if (!busy) setEditing(null);
          }}
        >
          <form
            className="project-form"
            onSubmit={async (e) => {
              e.preventDefault();
              if (busy) return;
              setBusy(true);
              setFormError("");
              try {
                const result = await projectApi(projectId)(
                  editing.id ? `/projects/${editing.id}` : "/projects",
                  editing.id ? "PUT" : "POST",
                  { name, type },
                );
                setProjects((rows) =>
                  editing.id
                    ? rows.map((p) => (p.id === result.id ? result : p))
                    : [...rows, result],
                );
                setEditing(null);
                select(result.id);
              } catch (e) {
                setFormError(e.message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <div className="modal-heading">
              <h2>{editing.id ? "Edit project" : "Create a project"}</h2>
              <IconButton
                title="Close project form"
                type="button"
                disabled={busy}
                onClick={() => setEditing(null)}
              >
                <X size={18} />
              </IconButton>
            </div>
            <p>
              {editing.id
                ? "Update the name and type for this project."
                : `Start with model profiles copied from ${project.name}. Your new project gets its own workspace, settings and conversations.`}
            </p>
            <Field label="Project name">
              <input
                autoFocus
                required
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="What are you working on?"
              />
            </Field>
            <Field label="Project type">
              <select value={type} onChange={(e) => setType(e.target.value)}>
                {types.map((t) => (
                  <option key={t} value={t}>
                    {t[0].toUpperCase() + t.slice(1)}
                  </option>
                ))}
              </select>
            </Field>
            {!editing.id && (
              <p className="muted">
                A local project folder is created automatically. You can select
                an existing source folder on the Setup page.
              </p>
            )}
            {formError && (
              <p role="alert" className="error-banner">
                {formError}
              </p>
            )}
            <button className="primary" disabled={busy || !name.trim()}>
              {busy
                ? "Saving…"
                : editing.id
                  ? "Save project"
                  : "Create project"}
              <ArrowRight size={16} />
            </button>
          </form>
        </Dialog>
      )}
    </>
  );
}
