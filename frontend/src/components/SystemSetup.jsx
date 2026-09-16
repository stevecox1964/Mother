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
        <button
          className={cx(tab === "web" && "selected")}
          onClick={() => setTab("web")}
        >
          Web tools
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
      ) : tab === "folders" ? (
        <SharedFolders settings={settings} setSettings={updated} fail={fail} />
      ) : (
        <WebToolsSetup settings={settings} refresh={refresh} fail={fail} />
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

export function WebToolsSetup({ settings, refresh, fail }) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="settings-page">
      <div className="page-heading">
        <div>
          <h1>Web tools</h1>
          <p>
            Models search the web and read pages through Browserbase. Web
            requests are paid on your Browserbase account.
          </p>
        </div>
        <button
          className="primary"
          disabled={busy || !key}
          onClick={async () => {
            setBusy(true);
            try {
              await globalApi("/credentials", "PUT", {
                name: "BROWSERBASE_API_KEY",
                value: key.trim(),
              });
              setKey("");
              await refresh();
            } catch (e) {
              fail(e);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Saving…" : "Save key"}
        </button>
      </div>
      <div className="project-body">
        <Field
          label="Browserbase API key"
          hint={
            (settings.web_key_set
              ? "A key is saved. web_search and web_fetch are available."
              : "No key saved. Web tools stay hidden from models.") +
            " Stored separately on this machine and never displayed again."
          }
        >
          <input
            type="password"
            autoComplete="new-password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="Paste Browserbase API key"
          />
        </Field>
        <div className="form-note">
          Web pages are untrusted. A page can contain text that tries to steer a
          model. Turn web tools off per project or per model in their tool
          lists.
        </div>
      </div>
    </div>
  );
}
