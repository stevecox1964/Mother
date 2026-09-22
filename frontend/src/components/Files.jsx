import { useEffect, useState } from "react";
import { FileText, Folder, RefreshCw } from "lucide-react";
import { cx, IconButton } from "./ui";

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

// Read-only view of the project folder.
export function Files({ api, fail }) {
  const [list, setList] = useState(null);
  const [file, setFile] = useState(null);
  const load = async () => {
    try {
      setList(await api("/files"));
    } catch (e) {
      fail(e);
    }
  };
  const open = async (path) => {
    try {
      setFile(await api("/files/content?" + new URLSearchParams({ path })));
    } catch (e) {
      fail(e);
    }
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
        {list?.truncated && (
          <p className="muted">List is cut short. The folder is very big.</p>
        )}
        {list && !list.files.length && (
          <p className="muted">No text files in this project folder yet.</p>
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
              <span className="muted">Read only · {file.bytes} bytes</span>
            </div>
            <pre>{file.content}</pre>
          </>
        ) : (
          <p className="muted">Pick a file to see it.</p>
        )}
      </section>
    </div>
  );
}
