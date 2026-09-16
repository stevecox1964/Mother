import { useEffect, useRef, useState } from "react";
import { Check, Database, Plus, Send, Settings2, Trash2 } from "lucide-react";
import { names, cx, Avatar, IconButton, Field } from "./ui";

export function ModelSettings({ settings, setSettings, fail, refresh, api }) {
  const [form, setForm] = useState(() => structuredClone(settings)),
    [selected, setSelected] = useState(settings.models[0]?.id),
    [key, setKey] = useState(""),
    [saved, setSaved] = useState(false),
    [busy, setBusy] = useState(false),
    [keySaved, setKeySaved] = useState(false),
    [catalog, setCatalog] = useState(null),
    [catalogError, setCatalogError] = useState(""),
    [catalogBusy, setCatalogBusy] = useState(false);
  const catalogRequest = useRef(0);
  const model = form.models.find((m) => m.id === selected);
  const savedModel = settings.models.find((m) => m.id === selected);
  // A new profile can discover models through an existing saved connection.
  const catalogConnection =
    model &&
    settings.models.find((p) =>
      ["provider", "base_url", "api_key_env"].every((k) => model[k] === p[k]),
    );
  useEffect(() => {
    catalogRequest.current += 1;
    setCatalog(null);
    setCatalogError("");
    setCatalogBusy(false);
    return () => {
      catalogRequest.current += 1;
    };
  }, [selected, model?.provider, model?.base_url, model?.api_key_env]);
  const fetchModels = async () => {
    const requestId = ++catalogRequest.current;
    setCatalogBusy(true);
    setCatalogError("");
    setCatalog(null);
    try {
      const result = await api(
        `/providers/${model.provider}/models?profile_id=${encodeURIComponent(catalogConnection.id)}`,
      );
      if (requestId === catalogRequest.current) setCatalog(result);
    } catch (e) {
      if (requestId === catalogRequest.current) setCatalogError(e.message);
    } finally {
      if (requestId === catalogRequest.current) setCatalogBusy(false);
    }
  };
  const change = (k, v) => {
    setForm({ ...form, [k]: v });
    setSaved(false);
  };
  const update = (patch) => {
    setForm({
      ...form,
      models: form.models.map((m) =>
        m.id === selected ? { ...m, ...patch } : m,
      ),
    });
    setSaved(false);
  };
  const save = async (e) => {
    e?.preventDefault();
    setBusy(true);
    try {
      const value = await api("/settings", "PUT", form);
      setSettings(value);
      setForm(structuredClone(value));
      setSaved(true);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };
  const add = () => {
    const id = "model-" + Date.now();
    const provider = model?.provider || "openai";
    const defaults = settings.providers.find((p) => p.id === provider);
    const m = {
      id,
      name: `New ${names[provider]} model`,
      provider,
      model: provider === "demo" ? "simulated" : "",
      soul: "Answer the user clearly and concisely. Use evidence when relevant.",
      enabled: true,
      context_mode: "board",
      vision: false,
      base_url: model?.base_url ?? defaults.base_url,
      api_key_env: model?.api_key_env ?? defaults.api_key_env,
      max_tokens: 4096,
      tools_enabled: true,
    };
    setForm({ ...form, models: [...form.models, m] });
    setSelected(id);
    setKey("");
    setKeySaved(false);
    setSaved(false);
  };
  return (
    <div className="settings-page">
      <div className="page-heading">
        <div>
          <h1>System model registry</h1>
          <p>
            Manage models and provider credentials for all projects.
            Instructions here are defaults for new project assignments.
          </p>
        </div>
        <button className="primary" onClick={save} disabled={busy}>
          {saved ? <Check size={16} /> : <Settings2 size={16} />}{" "}
          {busy ? "Saving…" : saved ? "Saved" : "Save configuration"}
        </button>
      </div>
      <div className="settings-body">
        <div className="ensemble-controls">
          <Field label="Default chat model">
            <select
              value={form.chief_id}
              onChange={(e) => change("chief_id", e.target.value)}
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
                className={cx(selected === m.id && "selected")}
                key={m.id}
                onClick={() => {
                  setSelected(m.id);
                  setKey("");
                  setKeySaved(false);
                }}
              >
                <Avatar small name={m.name} provider={m.provider} />
                <span>
                  {m.name}
                  <small>
                    {names[m.provider]}
                    {!m.enabled ? " · disabled" : ""}
                  </small>
                </span>
              </button>
            ))}
            <button
              className="add-model"
              onClick={add}
              disabled={form.models.length >= 64}
            >
              <Plus size={16} />
              {model ? `Add ${names[model.provider]} model` : "Add model"}
            </button>
          </div>
          {model ? (
            <form className="model-form" onSubmit={save}>
              <div className="model-form-title">
                <Avatar name={model.name} provider={model.provider} />
                <h2>{model.name}</h2>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={model.enabled}
                    onChange={(e) => update({ enabled: e.target.checked })}
                  />
                  Enabled
                </label>
                <IconButton
                  title="Remove model from system (disables its project assignments)"
                  type="button"
                  onClick={() => {
                    const models = form.models.filter((m) => m.id !== selected);
                    setForm({
                      ...form,
                      models,
                      chief_id: form.chief_id === selected ? "" : form.chief_id,
                    });
                    setSelected(models[0]?.id);
                    setSaved(false);
                  }}
                >
                  <Trash2 size={16} />
                </IconButton>
              </div>
              <div className="form-grid">
                <Field label="Display name">
                  <input
                    value={model.name}
                    onChange={(e) => update({ name: e.target.value })}
                    required
                    maxLength={80}
                  />
                </Field>
                <Field label="Provider">
                  <select
                    value={model.provider}
                    onChange={(e) => {
                      const p = settings.providers.find(
                        (p) => p.id === e.target.value,
                      );
                      const connection =
                        settings.models.find(
                          (m) => m.provider === p.id && m.key_set,
                        ) || settings.models.find((m) => m.provider === p.id);
                      update({
                        provider: p.id,
                        base_url: connection?.base_url ?? p.base_url,
                        api_key_env: connection?.api_key_env ?? p.api_key_env,
                        model: p.id === "demo" ? "simulated" : "",
                        ...(!savedModel
                          ? { name: `New ${names[p.id]} model` }
                          : {}),
                      });
                      setKey("");
                      setKeySaved(false);
                    }}
                  >
                    {settings.providers.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <div className="model-id-field">
                  <Field
                    label="Model ID"
                    hint="Enter an exact ID or fetch the provider’s current list."
                  >
                    <input
                      aria-label="Model ID"
                      value={model.model}
                      placeholder="Enter a model ID"
                      onChange={(e) => update({ model: e.target.value })}
                    />
                  </Field>
                  <div className="catalog-controls">
                    <button
                      type="button"
                      className="secondary catalog-fetch"
                      onClick={fetchModels}
                      disabled={catalogBusy || !catalogConnection}
                    >
                      {catalogBusy ? "Fetching models…" : "Fetch models"}
                    </button>
                    {!catalogConnection && (
                      <small>Save the connection settings first.</small>
                    )}
                    {!savedModel && catalogConnection && (
                      <small>
                        Uses your saved {names[model.provider]} connection. Pick
                        a model, then save to add it to chat.
                      </small>
                    )}
                    {catalogError && (
                      <small className="catalog-error" role="alert">
                        {catalogError}
                      </small>
                    )}
                    {catalog && (
                      <>
                        <select
                          aria-label="Available provider models"
                          value=""
                          onChange={(e) => {
                            const choice = catalog.models.find(
                              (m) => m.id === e.target.value,
                            );
                            const previous = catalog.models.find(
                              (m) => m.id === model.model,
                            );
                            const autoName =
                              !savedModel &&
                              (model.name.startsWith("New ") ||
                                model.name === previous?.name);
                            update({
                              model: choice.id,
                              ...(autoName
                                ? { name: choice.name.slice(0, 80) }
                                : {}),
                            });
                          }}
                        >
                          <option value="" disabled>
                            {catalog.models.length
                              ? `Choose from ${catalog.models.length} models`
                              : "No models returned"}
                          </option>
                          {catalog.models.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.name === m.id ? m.id : `${m.name} · ${m.id}`}
                            </option>
                          ))}
                        </select>
                        <small role="status">
                          {catalog.truncated
                            ? "Partial provider list. "
                            : "Live provider list. "}
                          Some models may not support chat or tools. Choose an
                          ID, then save.
                        </small>
                      </>
                    )}
                  </div>
                </div>
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
              </div>
              <Field
                label="Soul · identity and working instructions"
                hint="What this model values, how it challenges ideas, and what it contributes."
              >
                <textarea
                  className="soul-input"
                  value={model.soul}
                  onChange={(e) => update({ soul: e.target.value })}
                  maxLength={20000}
                />
              </Field>
              <Field
                label="Expertise & knowledge"
                hint="Describe what this model knows about: components, architecture, domain knowledge, or responsibilities. This helps it decide whether to offer an answer; it does not load files or create memory."
              >
                <textarea
                  className="soul-input"
                  value={model.expertise || ""}
                  maxLength={4000}
                  placeholder="For example: navigation and pathfinding; understands the APC movement code."
                  onChange={(e) => update({ expertise: e.target.value })}
                />
              </Field>
              <div className="form-grid">
                <Field label="Context access">
                  <select
                    value={model.context_mode}
                    onChange={(e) => update({ context_mode: e.target.value })}
                  >
                    <option value="board">Shared board only</option>
                    <option value="files">Shared board + selected code</option>
                  </select>
                </Field>
                <Field
                  label="Image input"
                  hint="Enable only for a model that accepts images."
                >
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={model.vision}
                      onChange={(e) => update({ vision: e.target.checked })}
                    />
                    Send attached images
                  </label>
                </Field>
              </div>
              {model.context_mode === "files" && (
                <Field
                  label="Files for this model"
                  hint="Choose from the project's Setup page. Other models can learn from this model's posted findings, but receive only their own assigned source files."
                >
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={model.context_files == null}
                      onChange={(e) =>
                        update({ context_files: e.target.checked ? null : [] })
                      }
                    />
                    All selected project files
                  </label>
                  {model.context_files != null && (
                    <div className="assigned-files">
                      {[
                        ...new Set([
                          ...(form.context_files || []),
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
                            " (not selected in Setup)"}
                        </label>
                      ))}
                      {!form.context_files?.length && (
                        <p>Select files on the Setup page first.</p>
                      )}
                    </div>
                  )}
                </Field>
              )}
              <Field
                label="Model tools"
                hint="Lets this model inspect settings and look up provider model names during chat. Disable for models without tool support."
              >
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={model.tools_enabled !== false}
                    onChange={(e) =>
                      update({ tools_enabled: e.target.checked })
                    }
                  />
                  Allow read-only model lookups
                </label>
              </Field>
              {model.provider !== "demo" && (
                <>
                  <Field label="API base URL">
                    <input
                      value={model.base_url}
                      onChange={(e) => update({ base_url: e.target.value })}
                      placeholder="https://…/v1"
                    />
                  </Field>
                  <Field
                    label="Credential environment variable"
                    hint="Leave empty for a compatible local endpoint that needs no key."
                  >
                    <input
                      value={model.api_key_env}
                      onChange={(e) => {
                        update({ api_key_env: e.target.value });
                        setKeySaved(false);
                      }}
                      placeholder="PROVIDER_API_KEY"
                    />
                  </Field>
                  {model.api_key_env && (
                    <div className="credential-box">
                      <div>
                        <strong>Provider credential</strong>
                        <small>
                          {keySaved
                            ? "Credential saved"
                            : settings.models.some(
                                  (m) =>
                                    m.api_key_env === model.api_key_env &&
                                    m.key_set,
                                )
                              ? "A credential is configured"
                              : "No credential configured"}{" "}
                          · Stored separately on this machine
                        </small>
                      </div>
                      <input
                        aria-label="API key"
                        type="password"
                        autoComplete="new-password"
                        value={key}
                        onChange={(e) => setKey(e.target.value)}
                        placeholder="Paste API key (never displayed again)"
                      />
                      <button
                        type="button"
                        className="secondary"
                        disabled={!key}
                        onClick={async () => {
                          try {
                            await api("/credentials", "PUT", {
                              name: model.api_key_env,
                              value: key,
                            });
                            setKey("");
                            setKeySaved(true);
                            await refresh();
                          } catch (e) {
                            fail(e);
                          }
                        }}
                      >
                        Save key
                      </button>
                    </div>
                  )}
                </>
              )}
              <div className="form-note">
                Changes take effect on the next message after you save. Existing
                discussions keep their original configuration snapshot.
              </div>
            </form>
          ) : (
            <div className="no-model">
              Add a model to start building your ensemble.
            </div>
          )}
        </div>
        <div className="storage-location">
          <Database size={16} />
          <span>
            Local storage <code>{settings.storage_path}</code>
          </span>
        </div>
      </div>
    </div>
  );
}
