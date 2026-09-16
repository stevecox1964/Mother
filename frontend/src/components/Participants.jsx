import {
  ChevronRight,
  Code2,
  FolderOpen,
  MessagesSquare,
  Plus,
  X,
  FlaskConical,
  VolumeX,
  Volume2,
} from "lucide-react";
import { names, cx, Avatar, IconButton } from "./ui";

// Right-hand panel: who receives a broadcast, who is squelched, project context.
export function Participants({
  enabled,
  settings,
  close,
  navigate,
  broadcastTargets,
  setBroadcastTargets,
  toggleRecipient,
  squelched,
  toggleSquelch,
  voiceBusy,
  conversationReady,
  cid,
  simulated,
  demo,
}) {
  return (
    <aside
      className="ensemble-panel"
      id="participants-panel"
      aria-label="Participants"
    >
      <div className="panel-title">
        <h2>Participants</h2>
        <IconButton title="Close participants" onClick={close}>
          <X size={18} />
        </IconButton>
      </div>
      <div className="members">
        <p className="squelch-help">
          Squelch silences a model in this conversation, including pending
          replies. Unsquelch lets it join future messages or messages.
        </p>
        <button className="secondary" onClick={() => setBroadcastTargets(null)}>
          Select all for broadcast
        </button>
        {enabled.map((m) => (
          <div className="member" key={m.id}>
            <input
              type="checkbox"
              aria-label={"Include " + m.name + " in broadcast"}
              checked={
                broadcastTargets === null || broadcastTargets.includes(m.id)
              }
              onChange={() => toggleRecipient(m.id)}
            />
            <Avatar name={m.name} provider={m.provider} />
            <div>
              <strong>{m.name}</strong>
              <small>
                {names[m.provider]} ·{" "}
                {m.provider === "demo"
                  ? "simulated"
                  : m.ready
                    ? "configured"
                    : "key needed"}
              </small>
              <span className="context-tag">
                {m.context_mode === "files" ? (
                  <Code2 size={10} />
                ) : (
                  <MessagesSquare size={10} />
                )}{" "}
                {m.context_mode === "files" ? "Selected code" : "Board context"}
                {m.vision ? " + images" : ""}
              </span>
            </div>
            <button
              className={cx("squelch-button", squelched(m.id) && "muted")}
              aria-label={
                (squelched(m.id) ? "Unsquelch " : "Squelch ") + m.name
              }
              aria-pressed={squelched(m.id)}
              disabled={voiceBusy.includes(m.id) || (cid && !conversationReady)}
              onClick={() => toggleSquelch(m)}
            >
              {squelched(m.id) ? <Volume2 size={14} /> : <VolumeX size={14} />}{" "}
              {squelched(m.id) ? "Unsquelch" : "Squelch"}
            </button>
          </div>
        ))}
      </div>
      <button className="add-model" onClick={() => navigate("settings")}>
        <Plus size={15} />
        Manage models
      </button>
      <div className="context-summary">
        <FolderOpen size={16} />
        <span>
          {settings.project_path
            ? settings.project_path.split(/[\\/]/).pop()
            : "No project attached"}
          <small>{settings.context_files.length} selected source files</small>
        </span>
        <button
          onClick={() => navigate("project")}
          aria-label="Configure project"
        >
          <ChevronRight size={16} />
        </button>
      </div>
      {!simulated && (
        <button className="demo-button" onClick={demo}>
          <FlaskConical size={15} />
          Try simulated chat
        </button>
      )}
      {cid && (
        <a
          className="subtle-link"
          href={"/api/conversations/" + cid + "/export"}
        >
          Export conversation as JSONL
        </a>
      )}
    </aside>
  );
}
