import { useEffect, useRef, useState } from "react";
import { FileText, Folder, RefreshCw, Upload } from "lucide-react";
import { cx, IconButton } from "./ui";

// Must match workspace.MEDIA on the server. Other files open as text.
const MEDIA = /\.(png|jpe?g|gif|webp|pdf)$/i;
export const ACCEPT =
  ".png,.jpg,.jpeg,.gif,.webp,.pdf,.py,.js,.jsx,.ts,.tsx,.css,.html,.md,.txt,.json,.toml,.yaml,.yml,.sql,.rs,.go,.c,.cpp,.h,.cs,.sh,.ps1";

function readBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = () => reject(Error(`Could not read ${file.name}.`));
    reader.readAsDataURL(file);
  });
}

// Upload one by one so one bad file does not stop the rest.
export async function uploadFiles(api, files, folder) {
  const dir = folder.trim().replace(/^\/+|\/+$/g, "");
  const saved = [];
  const failed = [];
  for (const f of files) {
    const path = dir ? `${dir}/${f.name}` : f.name;
    try {
      saved.push(
        await api("/files/upload", "POST", {
          path,
          base64: await readBase64(f),
        }),
      );
    } catch (e) {
      failed.push(`${path}: ${e.message}`);
    }
  }
  return { saved, failed };
}

// Turn flat "a/b/c.py" paths into nested folders.
function buildTree(files) {
  const root = { folders: {}, files: [] };
  for (const f of files) {
    const parts = f.path.split("/");
    let node = root;
    for (const part of parts.slice(0, -1))
      node = node.folders[part] ??= { folders: {}, files: [] };
    node.files.push({ ...f, name: parts.at(-1) });
  }
  return root;
}

function Tree({ node, open, current }) {
  return (
    <>
      {Object.entries(node.folders).map(([name, child]) => (
        <details key={name}>
          <summary>
            <Folder size={14} />
            {name}
          </summary>
          <div className="files-tree-children">
            <Tree node={child} open={open} current={current} />
          </div>
        </details>
      ))}
      {node.files.map((f) => (
        <button
          key={f.path}
          className={cx(current === f.path && "selected")}
          title={f.path}
          onClick={() => open(f.path)}
        >
          <FileText size={14} />
          {f.name}
        </button>
      ))}
    </>
  );
}

// View of the project folder. Files can be uploaded but not edited here.
export function Files({ api, projectId, fail }) {
  const [list, setList] = useState(null);
  const [file, setFile] = useState(null);
  const [folder, setFolder] = useState("");
  const [status, setStatus] = useState("");
  const picker = useRef(null);
  const load = async () => {
    try {
      setList(await api("/files"));
    } catch (e) {
      fail(e);
    }
  };
  const open = async (path) => {
    if (MEDIA.test(path)) {
      const query = new URLSearchParams({ project_id: projectId, path });
      return setFile({ path, url: `/api/files/raw?${query}` });
    }
    try {
      setFile(await api("/files/content?" + new URLSearchParams({ path })));
    } catch (e) {
      fail(e);
    }
  };
  const upload = async (files) => {
    const { saved, failed } = await uploadFiles(api, files, folder);
    const replaced = saved.filter((r) => r.replaced).length;
    setStatus(
      `Uploaded ${saved.length} of ${files.length} files.` +
        (replaced ? ` Replaced ${replaced} (old versions kept in backups).` : "") +
        (failed.length ? ` Not uploaded: ${failed.join("; ")}` : ""),
    );
    picker.current.value = "";
    load();
  };
  useEffect(() => {
    load();
  }, []);
  return (
    <div className="files-page">
      <nav className="files-tree" aria-label="Project files">
        <div className="files-tree-head">
          <span>{list ? `${list.files.length} files` : "Loading…"}</span>
          <IconButton title="Refresh files" onClick={load}>
            <RefreshCw size={14} />
          </IconButton>
        </div>
        <div className="files-upload">
          <input
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            placeholder="Folder (empty = top)"
            aria-label="Upload folder"
          />
          <IconButton
            title="Upload files"
            onClick={() => picker.current.click()}
          >
            <Upload size={14} />
          </IconButton>
          <input
            ref={picker}
            type="file"
            multiple
            hidden
            accept={ACCEPT}
            onChange={(e) => upload([...e.target.files])}
          />
        </div>
        {status && <p className="muted">{status}</p>}
        {list?.truncated && (
          <p className="muted">List is cut short. The folder is very big.</p>
        )}
        {list && !list.files.length && (
          <p className="muted">No files in this project folder yet.</p>
        )}
        {list && (
          <Tree node={buildTree(list.files)} open={open} current={file?.path} />
        )}
      </nav>
      <section className="files-view" aria-label="File contents">
        {file ? (
          <>
            <div className="files-view-head">
              <code>{file.path}</code>
              {file.url ? (
                <a href={file.url} target="_blank" rel="noreferrer">
                  Open in new tab
                </a>
              ) : (
                <span className="muted">Read only · {file.bytes} bytes</span>
              )}
            </div>
            {!file.url ? (
              <pre>{file.content}</pre>
            ) : /\.pdf$/i.test(file.path) ? (
              <iframe className="files-pdf" src={file.url} title={file.path} />
            ) : (
              <img className="files-image" src={file.url} alt={file.path} />
            )}
          </>
        ) : (
          <p className="muted">Pick a file to see it.</p>
        )}
      </section>
    </div>
  );
}
