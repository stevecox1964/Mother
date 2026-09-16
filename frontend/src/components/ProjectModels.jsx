import { useEffect, useState } from "react";
import { api as globalApi } from "../api";
import { names, cx, Avatar, Field, ToolChecklist } from "./ui";

export function ProjectModels({
  settings,
  setSettings,
  fail,
  api,
  openSystem,
}) {
  const [form, setForm] = useState(() => structuredClone(settings));
  const [registry, setRegistry] = useState([]);
  const [selected, setSelected] = useState(settings.models[0]?.id);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    globalApi("/system/settings")
      .then((r) => setRegistry(r.models))
      .catch(fail);
  }, []);
  const model = form.models.find((m) => m.id === selected);
  const update = (patch) => {
    setForm({
      ...form,
      models: form.models.map((m) =>
        m.id === selected ? { ...m, ...patch } : m,
      ),
    });
    setSaved(false);
  };
  const save = async () => {
    setBusy(true);
    try {
      const payload = {
        ...form,
        models: form.models.map((m) =>
          m.name.trim() || !m.system_name
            ? m
            : { ...m, name: m.system_name, name_alias: "" },
        ),
      };
      const value = await api("/settings", "PUT", payload);
      setSettings(value);
      setForm(structuredClone(value));
      setSaved(true);
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
          <h1>Models in this project</h1>
          <p>
            Choose participants and give each model its own instructions and
            context.
          </p>
        </div>
        <button className="primary" disabled={busy} onClick={save}>
          {busy ? "Saving…" : saved ? "Saved" : "Save project models"}
        </button>
      </div>
      <div className="settings-body">
        <div className="registry-add">
          <Field label="Add a system model to this project">
            <select
              value=""
              disabled={form.models.length >= 16}
              onChange={(e) => {
                const source = registry.find((m) => m.id === e.target.value);
                if (!source) return;
                const id = form.models.some((m) => m.id === source.id)
                  ? `model-${Date.now()}`
                  : source.id;
                const entry = {
                  ...source,
                  id,
                  system_model_id: source.id,
                  context_files: null,
                  enabled: true,
                  project_enabled: true,
                };
                setForm({
                  ...form,
                  models: [...form.models, entry],
                  chief_id: form.chief_id || id,
                });
                setSelected(id);
                setSaved(false);
              }}
            >
              <option value="">Choose a model…</option>
              {registry
                .filter(
                  (m) => !form.models.some((p) => p.system_model_id === m.id),
                )
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                    {!m.enabled ? " · disabled in system" : ""}
                  </option>
                ))}
            </select>
          </Field>
          <button className="secondary" onClick={openSystem}>
            Manage system models
          </button>
        </div>
        <div className="ensemble-controls">
          <Field label="Default direct-chat model">
            <select
              value={form.chief_id}
              onChange={(e) => {
                setForm({ ...form, chief_id: e.target.value });
                setSaved(false);
              }}
            >
              <option value="">Choose a model</option>
              {form.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="model-editor">
          <div className="model-list">
            {form.models.map((m) => (
              <button
                key={m.id}
                className={cx(selected === m.id && "selected")}
                onClick={() => setSelected(m.id)}
              >
                <Avatar small name={m.name} provider={m.provider} />
                <span>
                  {m.name}
                  <small>
                    {m.system_missing
                      ? "Removed from system"
                      : m.system_enabled === false
                        ? "System disabled"
                        : !(m.project_enabled ?? m.enabled)
                          ? "Project disabled"
                          : names[m.provider]}
                  </small>
                </span>
              </button>
            ))}
          </div>
          {model ? (
            <div className="model-form">
              <div className="model-form-title">
                <Avatar name={model.name} provider={model.provider} />
                <h2>{model.name}</h2>
                <button
                  className="secondary"
                  onClick={() => {
                    const models = form.models.filter((m) => m.id !== selected);
                    setForm({
                      ...form,
                      models,
                      chief_id:
                        form.chief_id === selected
                          ? models[0]?.id || ""
                          : form.chief_id,
                    });
                    setSelected(models[0]?.id);
                    setSaved(false);
                  }}
                >
                  Remove from project
                </button>
              </div>
              <p className="form-note">
                {names[model.provider]} · {model.model} · Mention with @
                {model.name} or @{model.id}. Provider connections are managed in
                System setup.
              </p>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={model.project_enabled ?? model.enabled}
                  onChange={(e) =>
                    update({
                      enabled: e.target.checked,
                      project_enabled: e.target.checked,
                    })
                  }
                />
                Enabled in this project
              </label>
              <Field
                label="Name in this project"
                hint={
                  model.name_alias
                    ? `Renaming "${model.system_name}" for this project only. Clear the box to follow System setup again.`
                    : "Follows the name in System setup. Type here to use a different name in this project."
                }
              >
                <input
                  value={model.name}
                  maxLength={80}
                  placeholder={model.system_name || ""}
                  onChange={(e) =>
                    update({
                      name: e.target.value,
                      name_alias:
                        e.target.value === model.system_name
                          ? ""
                          : e.target.value,
                    })
                  }
                />
              </Field>
              <Field label="Instructions / soul">
                <textarea
                  value={model.soul}
                  rows={6}
                  onChange={(e) => update({ soul: e.target.value })}
                />
              </Field>
              <Field label="Expertise & knowledge">
                <textarea
                  value={model.expertise || ""}
                  rows={3}
                  onChange={(e) => update({ expertise: e.target.value })}
                />
              </Field>
              <Field label="Selected source context">
                <select
                  value={model.context_mode}
                  onChange={(e) => update({ context_mode: e.target.value })}
                >
                  <option value="board">Conversation only</option>
                  <option value="files">Include selected project files</option>
                </select>
              </Field>
              {model.context_mode === "files" && (
                <Field label="Files for this model">
                  <select
                    value={
                      model.context_files === null ||
                      model.context_files === undefined
                        ? "all"
                        : "assigned"
                    }
                    onChange={(e) =>
                      update({
                        context_files: e.target.value === "all" ? null : [],
                      })
                    }
                  >
                    <option value="all">All selected project files</option>
                    <option value="assigned">Choose a subset</option>
                  </select>
                  {Array.isArray(model.context_files) && (
                    <div className="assigned-files">
                      {[
                        ...new Set([
                          ...form.context_files,
                          ...model.context_files,
                        ]),
                      ].map((path) => (
                        <label className="checkbox" key={path}>
                          <input
                            type="checkbox"
                            checked={model.context_files.includes(path)}
                            onChange={(e) =>
                              update({
                                context_files: e.target.checked
                                  ? [...model.context_files, path]
                                  : model.context_files.filter(
                                      (f) => f !== path,
                                    ),
                              })
                            }
                          />
                          {path}
                          {!form.context_files.includes(path) &&
                            " (not selected)"}
                        </label>
                      ))}
                    </div>
                  )}
                </Field>
              )}
              <Field label="Output token limit">
                <input
                  type="number"
                  min={128}
                  max={32768}
                  value={model.max_tokens}
                  onChange={(e) =>
                    update({ max_tokens: Number(e.target.value) })
                  }
                />
              </Field>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={model.tools_enabled !== false}
                  onChange={(e) => update({ tools_enabled: e.target.checked })}
                />
                Allow tools under this project's folder permissions
              </label>
              {model.tools_enabled !== false && (
                <div className="field">
                  <span>Tools for this model</span>
                  <ToolChecklist
                    value={model.tools ?? null}
                    onChange={(tools) => update({ tools })}
                  />
                  <small>
                    The project's tool list and folder access still apply.
                  </small>
                </div>
              )}
            </div>
          ) : (
            <div className="no-model">
              Choose a system model above to add the first participant.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
