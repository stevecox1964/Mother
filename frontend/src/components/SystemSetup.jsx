import { useEffect, useState } from "react";
import { api as globalApi } from "../api";
import { cx, Field } from "./ui";
import { ModelSettings } from "./ModelSettings";

export function SystemSetup({ fail, refreshProject }) {
  const [settings, setSettings] = useState(null);
  const [tab, setTab] = useState("models");
  const refresh = () => globalApi("/system/settings").then(setSettings);
  useEffect(() => {
    refresh().catch(fail);
  }, []);
  const systemApi = (path, method, data) =>
    globalApi(path === "/credentials" ? path : `/system${path}`, method, data);
  if (!settings)
    return <div className="setup-loading">Loading system configuration…</div>;
  const updated = (value) => {
    setSettings(value);
    refreshProject().catch(fail);
  };
  return (
    <>
      <div className="setup-tabs" aria-label="System setup sections">
        <button
          className={cx(tab === "models" && "selected")}
          onClick={() => setTab("models")}
        >
          Model registry
        </button>
        <button
          className={cx(tab === "folders" && "selected")}
          onClick={() => setTab("folders")}
        >
          Shared folders
        </button>
      </div>
      {tab === "models" ? (
        <ModelSettings
          settings={settings}
          setSettings={updated}
          fail={fail}
          refresh={refresh}
          api={systemApi}
        />
      ) : (
        <SharedFolders settings={settings} setSettings={updated} fail={fail} />
      )}
    </>
  );
}

export function SharedFolders({ settings, setSettings, fail }) {
  const [paths, setPaths] = useState(
    settings.shared_paths || { tools: "", docs: "" },
  );
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <div className="settings-page">
      <div className="page-heading">
        <div>
          <h1>Shared system folders</h1>
          <p>
            Available to models in every project through read-only file tools.
          </p>
        </div>
        <button
          className="primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              setSettings(
                await globalApi("/system/settings", "PUT", {
                  ...settings,
                  shared_paths: paths,
                }),
              );
              setSaved(true);
            } catch (e) {
              fail(e);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Saving…" : saved ? "Saved" : "Save shared folders"}
        </button>
      </div>
      <div className="project-body">
        {["tools", "docs"].map((name) => (
          <Field
            key={name}
            label={`/${name} · Read only`}
            hint={`Models use /${name}/filename to read from this folder. Leave blank to disable it.`}
          >
            <input
              value={paths[name] || ""}
              placeholder={`Full path to the shared ${name} folder`}
              onChange={(e) => {
                setPaths({ ...paths, [name]: e.target.value });
                setSaved(false);
              }}
            />
          </Field>
        ))}
        <div className="form-note">
          Shared folders cannot be written through model tools, even if they
          overlap a project folder. The /tools folder contains reference
          material; reading it does not execute its contents.
        </div>
      </div>
    </div>
  );
}
