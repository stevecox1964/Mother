import { useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  ImagePlus,
  Plus,
  Hash,
  Users,
  MessageCircle,
  Search,
  Send,
  Settings2,
  Square,
  X,
  FlaskConical,
  PanelLeftClose,
  VolumeX,
  Volume2,
  Radio,
  SquareCode,
  ListRestart,
  CircleStop,
} from "lucide-react";
import { api as globalApi, projectApi } from "../api";
import { mentionRecipient } from "../mentions";
import { saveToFile } from "../utils/saveToFile";
import { date, cx, Avatar, IconButton } from "./ui";
import { Post } from "./Post";
import { Cell } from "./Cell";
import { SystemSetup } from "./SystemSetup";
import { ProjectModels } from "./ProjectModels";
import { ProjectSettings } from "./ProjectSettings";
import { Archive } from "./Archive";
import { ACCEPT, Files, uploadFiles } from "./Files";
import { Sidebar } from "./Sidebar";
import { useConversationActions } from "./ConversationDialogs";
import { Participants } from "./Participants";

export function App({
  project,
  projects,
  selectProject,
  editProject,
  deleteProject,
  openDeletedProjects,
}) {
  const api = projectApi(project.id);
  const [mode, setMode] = useState("broadcast"),
    [broadcastTargets, setBroadcastTargets] = useState(null),
    [discussionRounds, setDiscussionRounds] = useState(2);
  const [participation, setParticipation] = useState([]),
    [voiceBusy, setVoiceBusy] = useState([]),
    [conversationReady, setConversationReady] = useState(false);
  const mergeParticipation = (rows) =>
    setParticipation((previous) => {
      const byId = new Map(previous.map((p) => [p.model_id, p]));
      for (const row of rows || [])
        if ((byId.get(row.model_id)?.revision ?? -1) <= row.revision)
          byId.set(row.model_id, row);
      return [...byId.values()];
    });
  const [settings, setSettings] = useState(null),
    [conversations, setConversations] = useState([]),
    [cid, setCid] = useState(null);
  const [view, setView] = useState("board"),
    [events, setEvents] = useState([]),
    [runs, setRuns] = useState([]),
    [cells, setCells] = useState([]),
    [error, setError] = useState("");
  const [draft, setDraft] = useState(""),
    [images, setImages] = useState([]),
    [target, setTarget] = useState(""),
    [sending, setSending] = useState(false);
  const [mobile, setMobile] = useState(false),
    [participantsOpen, setParticipantsOpen] = useState(false);
  const fileRef = useRef(),
    projectFileRef = useRef(),
    timeline = useRef(),
    atBottom = useRef(true),
    selectedRef = useRef(null);
  selectedRef.current = cid;
  const fail = (e) => setError(e.message || String(e));
  const refreshSettings = () => api("/settings").then(setSettings);
  const refreshList = () => api("/conversations").then(setConversations);
  useEffect(() => {
    Promise.all([
      refreshSettings(),
      api("/conversations").then((list) => {
        setConversations(list);
        const last = localStorage.getItem(`mother-conversation-${project.id}`);
        if (list.length)
          setCid(list.find((c) => c.id === last)?.id || list[0].id);
      }),
    ]).catch(fail);
  }, []);
  useEffect(() => {
    if (cid) localStorage.setItem(`mother-conversation-${project.id}`, cid);
  }, [cid, project.id]);
  useEffect(() => {
    setEvents([]);
    setRuns([]);
    setCells([]);
    setParticipation([]);
    setConversationReady(false);
    if (!cid) return;
    let live = true,
      pending = false,
      after = 0;
    const poll = () => {
      if (pending) return;
      pending = true;
      return api("/conversations/" + cid + "?after=" + after)
        .then((data) => {
          if (live) {
            const fresh = data.events.filter((event) => event.seq > after);
            if (fresh.length) {
              after = Math.max(after, ...fresh.map((event) => event.seq));
              setEvents((previous) => [...previous, ...fresh]);
            }
            setRuns(data.runs);
            setCells(data.cells);
            mergeParticipation(data.participation);
            setConversationReady(true);
          }
        })
        .catch((e) => {
          if (live) fail(e);
        })
        .finally(() => {
          pending = false;
        });
    };
    poll();
    const id = setInterval(poll, 1200);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, [cid]);
  useEffect(() => {
    refreshList().catch(fail);
  }, [events.length]);
  const enabled = settings?.models.filter((m) => m.enabled) || [];
  const mention = mentionRecipient(draft, settings?.models || []);
  const mentionQuery =
    draft.trimStart().startsWith("@") && !mention?.model
      ? draft.trimStart().slice(1).toLowerCase()
      : null;
  const squelched = (id) =>
    Boolean(participation.find((p) => p.model_id === id)?.squelched);
  const recipients = enabled.filter(
    (m) =>
      (broadcastTargets === null || broadcastTargets.includes(m.id)) &&
      !squelched(m.id),
  );
  const toggleRecipient = (id) =>
    setBroadcastTargets((current) => {
      const chosen = current ?? enabled.map((m) => m.id);
      return chosen.includes(id)
        ? chosen.filter((x) => x !== id)
        : [...chosen, id];
    });
  useEffect(() => {
    if (!settings) return;
    const models = settings.models.filter((m) => m.enabled);
    setTarget((current) =>
      models.some((m) => m.id === current)
        ? current
        : models.find((m) => m.id === settings.chief_id)?.id ||
          models[0]?.id ||
          "",
    );
  }, [settings]);
  const active = runs.find((r) => r.status === "running");
  const title =
    conversations.find((c) => c.id === cid)?.title || "New conversation";
  const create = async (title) => {
    const c = await api("/conversations", "POST", { title });
    setCid(c.id);
    await refreshList();
    return c.id;
  };
  const { conversationMenu, openMenu, openTrash, newConversation, dialogs } =
    useConversationActions({
      api,
      fail,
      navigate: (v) => navigate(v),
      create,
      refreshList: setConversations,
      selectedRef,
      reset: (id) => {
        selectedRef.current = id;
        setCid(id);
        setDraft("");
        setImages([]);
        setEvents([]);
        setRuns([]);
      },
    });
  const send = async () => {
    if (!draft.trim() || sending || active || !enabled.length) return;
    if (cid && !conversationReady) return;
    if (mention?.error || mention?.empty) {
      setError(mention.error || "Write a message after the @model name.");
      return;
    }
    const sendMode = mention?.model ? "direct" : mode;
    const sendTarget = mention?.model?.id || target;
    if (sendMode !== "direct" && !recipients.length) {
      setError("Select or unsquelch at least one participant.");
      return;
    }
    if (
      sendMode === "direct" &&
      (!enabled.some((m) => m.id === sendTarget) || squelched(sendTarget))
    ) {
      setError("Choose a model for direct chat.");
      return;
    }
    setSending(true);
    setError("");
    try {
      const id = cid || (await create(draft.trim().slice(0, 70)));
      const run = await api("/conversations/" + id + "/messages", "POST", {
        content: draft,
        targets:
          sendMode !== "direct" ? recipients.map((m) => m.id) : [sendTarget],
        mode: sendMode,
        rounds: discussionRounds,
        images,
      });
      setDraft("");
      setImages([]);
      if (selectedRef.current === id || !cid) setRuns([run]);
      await refreshList();
    } catch (e) {
      fail(e);
    } finally {
      setSending(false);
    }
  };
  // Code cells: added by the user or from a model's Python block; run only on click.
  const updateCell = (cell) =>
    setCells((list) =>
      cell.deleted
        ? list.filter((c) => c.id !== cell.id)
        : list.some((c) => c.id === cell.id)
          ? list.map((c) => (c.id === cell.id ? cell : c))
          : [...list, cell],
    );
  const addCell = async (source = "") => {
    try {
      const id = cid || (await create("Code notebook"));
      updateCell(
        await api("/conversations/" + id + "/cells", "POST", { source }),
      );
    } catch (e) {
      fail(e);
    }
  };
  const runAll = () =>
    api("/conversations/" + cid + "/cells/run-all", "POST", {})
      .then((data) => setCells(data.cells))
      .catch(fail);
  const stopCode = () =>
    api("/conversations/" + cid + "/cells/stop", "POST", {}).catch(fail);
  const toggleSquelch = async (model) => {
    if (voiceBusy.includes(model.id)) return;
    setVoiceBusy((ids) => [...ids, model.id]);
    try {
      const value = !squelched(model.id);
      const id = cid || (await create("Project discussion"));
      const result = await api(
        "/conversations/" + id + "/models/" + model.id + "/squelch",
        "PUT",
        { squelched: value },
      );
      if (selectedRef.current === id || !cid) {
        mergeParticipation(result.participation);
        setRuns(result.runs);
      }
    } catch (e) {
      fail(e);
    } finally {
      setVoiceBusy((ids) => ids.filter((id) => id !== model.id));
    }
  };
  const attach = async (e) => {
    try {
      const files = Array.from(e.target.files || []);
      if (images.length + files.length > 2)
        throw Error("Attach up to two images.");
      const result = await Promise.all(
        files.map(
          (file) =>
            new Promise((resolve, reject) => {
              if (file.size > 4 * 1024 * 1024)
                return reject(Error("Each image must be under 4 MB."));
              const reader = new FileReader();
              reader.onload = () =>
                resolve({
                  name: file.name,
                  base64: reader.result.split(",")[1],
                  preview: reader.result,
                });
              reader.onerror = () => reject(Error("Could not read image."));
              reader.readAsDataURL(file);
            }),
        ),
      );
      setImages([...images, ...result]);
    } catch (e) {
      fail(e);
    } finally {
      e.target.value = "";
    }
  };
  // Save files into the project, then name them in the draft so models know.
  const addProjectFiles = async (e) => {
    const input = e.target;
    const { saved, failed } = await uploadFiles(
      api,
      [...input.files],
      "uploads",
    );
    input.value = "";
    if (saved.length) {
      const note =
        "Uploaded to project: " + saved.map((r) => r.path).join(", ");
      setDraft((d) => (d.trim() ? d.trimEnd() + "\n" : "") + note);
    }
    if (failed.length) fail(Error(`Not uploaded: ${failed.join("; ")}`));
  };
  const navigate = (v) => {
    setView(v);
    setMobile(false);
    setParticipantsOpen(false);
    setError("");
  };
  useEffect(() => {
    const close = (e) => {
      if (e.key === "Escape") {
        setMobile(false);
        setParticipantsOpen(false);
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);
  const demo = async () => {
    try {
      const cfg = structuredClone(settings);
      cfg.models.forEach((m) => {
        m.enabled = false;
        m.project_enabled = false;
      });
      const make = (id, name, soul) => ({
        id,
        name,
        soul,
        provider: "demo",
        model: "simulated",
        enabled: true,
        vision: false,
        base_url: "",
        api_key_env: "",
        context_mode: "board",
        max_tokens: 4096,
      });
      cfg.models = cfg.models
        .filter((m) => !m.id.startsWith("demo-"))
        .concat([
          make("demo-chief", "Demo assistant", "Answer the user concisely."),
          make("demo-critic", "Demo critic", "Question assumptions."),
          make("demo-builder", "Demo builder", "Propose an implementation."),
        ]);
      cfg.chief_id = "demo-chief";
      const system = await globalApi("/system/settings");
      for (const m of cfg.models.filter((m) => m.id.startsWith("demo-"))) {
        if (!system.models.some((p) => p.id === m.id))
          system.models.push({ ...m });
        m.system_model_id = m.id;
      }
      await globalApi("/system/settings", "PUT", system);
      setSettings(await api("/settings", "PUT", cfg));
    } catch (e) {
      fail(e);
    }
  };
  // Follow new posts only while the reader is already at the bottom.
  useEffect(() => {
    atBottom.current = true;
  }, [cid, view]);
  useEffect(() => {
    const el = timeline.current;
    if (el && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [events.length, active?.id, view, cid]);
  if (!settings)
    return (
      <div className="loading">
        <div className="brandmark">m</div>
        <h2>Opening Mother</h2>
        <p>{error || "Loading your local workspace…"}</p>
        {error && <button onClick={() => location.reload()}>Retry</button>}
      </div>
    );
  const simulated = enabled.some((m) => m.provider === "demo");
  const unready = (
    mode !== "direct" ? recipients : enabled.filter((m) => m.id === target)
  ).filter((m) => !m.ready);
  const cellById = Object.fromEntries(cells.map((c) => [c.id, c]));
  const codeBusy = cells.some(
    (c) => c.status === "queued" || c.status === "running",
  );
  const visible = events.filter(
    (e) =>
      e.kind !== "run" &&
      !(e.kind === "cell" && !cellById[e.metadata.cell_id]) &&
      !(e.kind === "system" && e.content === "Discussion complete."),
  );
  return (
    <div className="app">
      <Sidebar
        project={project}
        projects={projects}
        selectProject={selectProject}
        editProject={editProject}
        deleteProject={deleteProject}
        openDeletedProjects={openDeletedProjects}
        locked={sending || voiceBusy.length > 0}
        mobile={mobile}
        conversations={conversations}
        cid={cid}
        view={view}
        navigate={navigate}
        openConversation={(id) => {
          setCid(id);
          navigate("board");
        }}
        newConversation={newConversation}
        openTrash={openTrash}
        conversationMenu={conversationMenu}
        openConversationMenu={openMenu}
      />
      {mobile && (
        <button
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <main>
        <header>
          <div className="channel-title">
            <IconButton
              title="Toggle navigation"
              aria-expanded={mobile}
              onClick={() => setMobile(!mobile)}
            >
              <PanelLeftClose size={19} />
            </IconButton>
            {view === "board" && <Hash size={21} />}
            <div>
              <h1>
                {view === "board"
                  ? title
                  : {
                      archive: "Search conversations",
                      settings: "Models in this project",
                      project: "Project setup",
                      files: "Project files",
                      system: "System setup",
                    }[view]}
              </h1>
              <span className="scope-label">
                {view === "system"
                  ? "System · All projects on this machine"
                  : `Project · ${project.name}`}
              </span>
              {view === "board" && (
                <p>
                  {mode === "broadcast"
                    ? "Who knows about this?"
                    : mode === "opinions"
                      ? "Compare independent perspectives"
                      : `Chat with ${enabled.find((m) => m.id === target)?.name || "a model"}`}
                </p>
              )}
            </div>
          </div>
          {view === "board" && (
            <div className="heading-actions">
              {cid && (
                <IconButton
                  title="Export readable transcript"
                  onClick={() =>
                    saveToFile(
                      visible
                        .map(
                          (e) =>
                            `[${e.created_at}] ${e.author} · ${e.kind}\n${
                              e.kind === "cell"
                                ? "```python\n" +
                                  cellById[e.metadata.cell_id].source +
                                  "\n```"
                                : e.content
                            }`,
                        )
                        .join("\n\n"),
                      "mother",
                    )
                  }
                >
                  <ArrowDownToLine size={18} />
                </IconButton>
              )}
              {cells.length > 0 &&
                (codeBusy ? (
                  <IconButton title="Stop code" onClick={stopCode}>
                    <CircleStop size={18} />
                  </IconButton>
                ) : (
                  <IconButton
                    title="Restart and run all cells, top to bottom"
                    onClick={runAll}
                  >
                    <ListRestart size={18} />
                  </IconButton>
                ))}
              <button
                className={cx(
                  "participants-button",
                  participantsOpen && "selected",
                )}
                aria-expanded={participantsOpen}
                aria-label={`Participants (${enabled.length})`}
                aria-controls="participants-panel"
                onClick={() => setParticipantsOpen(!participantsOpen)}
              >
                <Users size={17} />
                <span>Participants</span>
                <span>{enabled.length}</span>
              </button>
            </div>
          )}
        </header>
        {error && (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <IconButton title="Dismiss error" onClick={() => setError("")}>
              <X size={16} />
            </IconButton>
          </div>
        )}
        {view === "project" && !project.is_main && (
          <div className="setup-tabs" aria-label="Project setup sections">
            <button onClick={() => editProject(project)}>Name & type</button>
          </div>
        )}
        {view === "system" ? (
          <SystemSetup fail={fail} refreshProject={refreshSettings} />
        ) : view === "settings" ? (
          <ProjectModels
            api={api}
            settings={settings}
            setSettings={setSettings}
            fail={fail}
            openSystem={() => navigate("system")}
          />
        ) : view === "project" ? (
          <ProjectSettings
            api={api}
            project={project}
            settings={settings}
            setSettings={setSettings}
            fail={fail}
          />
        ) : view === "files" ? (
          <Files api={api} projectId={project.id} fail={fail} />
        ) : view === "archive" ? (
          <Archive
            api={api}
            key={JSON.stringify(conversations.map((c) => [c.id, c.title]))}
            open={(id) => {
              setCid(id);
              navigate("board");
            }}
            fail={fail}
          />
        ) : (
          <>
            <div
              className={cx(
                "board-layout",
                participantsOpen && "with-participants",
              )}
            >
              <section className="discussion" aria-label="Conversation">
                <div className="discussion-controls">
                  <div
                    className="mode-switch"
                    role="group"
                    aria-label="Message mode"
                  >
                    <button
                      aria-pressed={mode === "broadcast"}
                      onClick={() => setMode("broadcast")}
                    >
                      <Radio size={14} />
                      Broadcast
                    </button>
                    <button
                      aria-pressed={mode === "opinions"}
                      onClick={() => setMode("opinions")}
                    >
                      Independent opinions
                    </button>
                    <button
                      aria-pressed={mode === "direct"}
                      onClick={() => setMode("direct")}
                    >
                      <MessageCircle size={14} />
                      Direct
                    </button>
                  </div>
                  <button
                    className="subtle-link"
                    onClick={() => setParticipantsOpen(true)}
                  >
                    Recipients & squelch
                  </button>
                  <button
                    className="subtle-link"
                    onClick={() => {
                      if (timeline.current)
                        timeline.current.scrollTop =
                          timeline.current.scrollHeight;
                    }}
                  >
                    Latest ↓
                  </button>
                </div>
                {active && (
                  <div className="live-voices" aria-label="Live participants">
                    {(active.members || []).map((member) => {
                      const model = enabled.find(
                        (m) => m.id === member.model_id,
                      );
                      if (!model) return null;
                      return (
                        <div
                          className={cx(
                            "voice-chip",
                            squelched(model.id) && "muted",
                          )}
                          key={model.id}
                        >
                          <span>
                            {model.name}
                            <small>
                              {squelched(model.id)
                                ? "Squelched"
                                : {
                                    discovery: "Checking knowledge",
                                    offered: "Has relevant knowledge",
                                    passed: "Passed",
                                    lead: "Answering first",
                                    review: "Checking for additions",
                                    update: "Updating answer",
                                  }[member.status] || member.status}
                              {active.mode === "opinions" && member.round
                                ? ` · round ${member.round}`
                                : ""}
                            </small>
                          </span>
                          <IconButton
                            title={
                              (squelched(model.id)
                                ? "Unsquelch "
                                : "Squelch ") + model.name
                            }
                            disabled={voiceBusy.includes(model.id)}
                            onClick={() => toggleSquelch(model)}
                          >
                            {squelched(model.id) ? (
                              <Volume2 size={15} />
                            ) : (
                              <VolumeX size={15} />
                            )}
                          </IconButton>
                        </div>
                      );
                    })}
                  </div>
                )}
                <div
                  className="timeline"
                  ref={timeline}
                  onScroll={(e) => {
                    const el = e.currentTarget;
                    atBottom.current =
                      el.scrollHeight - el.scrollTop - el.clientHeight < 80;
                  }}
                >
                  {!visible.length ? (
                    <div className="empty-board">
                      <div className="empty-icon">
                        <Hash size={27} />
                      </div>
                      <h2>{title}</h2>
                      <p>
                        Broadcast asks who knows about this. A relevant model
                        answers first; peers add only what is missing.
                      </p>
                      {!enabled.length && (
                        <button
                          className="secondary"
                          onClick={() => navigate("settings")}
                        >
                          Add your first model <ArrowRight size={15} />
                        </button>
                      )}
                    </div>
                  ) : (
                    <>
                      <div className="date-separator">
                        <span>
                          {date(visible[0].created_at)} · Conversation history
                        </span>
                      </div>
                      {visible.map((e) =>
                        e.kind === "cell" ? (
                          <Cell
                            key={e.id}
                            cell={cellById[e.metadata.cell_id]}
                            api={api}
                            fail={fail}
                            onChange={updateCell}
                          />
                        ) : (
                          <Post key={e.id} event={e} onMakeCell={addCell} />
                        ),
                      )}
                    </>
                  )}
                  {active && (
                    <div className="thinking">
                      <span className="thinking-dots">● ● ●</span>
                      <span>
                        {active.mode !== "direct"
                          ? "The models are collaborating…"
                          : "Writing a reply…"}
                        <span>
                          Models may pass. Squelch a voice to stop its
                          participation.
                        </span>
                      </span>
                    </div>
                  )}
                </div>
                <div className="compose-area">
                  {unready.length > 0 && (
                    <div className="setup-note">
                      <Settings2 size={16} />
                      <span>
                        {unready.length} enabled{" "}
                        {unready.length === 1 ? "model needs" : "models need"}{" "}
                        credentials.
                      </span>
                      <button onClick={() => navigate("settings")}>
                        Configure models <ArrowRight size={13} />
                      </button>
                    </div>
                  )}
                  {simulated && (
                    <div className="demo-note">
                      <FlaskConical size={15} />
                      Demo responses are simulated. No model API is called for
                      demo profiles.
                    </div>
                  )}
                  <div className="composer">
                    <div className="composer-top">
                      <span className="broadcast-label">
                        {mode !== "direct" ? (
                          <>
                            <Radio size={14} />
                            <span>{recipients.length} recipients</span>
                            <select
                              aria-label="Discussion depth"
                              value={discussionRounds}
                              onChange={(e) =>
                                setDiscussionRounds(Number(e.target.value))
                              }
                            >
                              <option value={1}>
                                {mode === "broadcast"
                                  ? "Find a speaker + answer"
                                  : "1 round · independent replies"}
                              </option>
                              <option value={2}>
                                {mode === "broadcast"
                                  ? "Answer + useful additions"
                                  : "2 rounds · replies + discussion"}
                              </option>
                              <option value={3}>
                                {mode === "broadcast"
                                  ? "Additions + optional answer update"
                                  : "3 rounds · deeper discussion"}
                              </option>
                            </select>
                          </>
                        ) : (
                          <>
                            <MessageCircle size={14} />
                            <select
                              aria-label="Chat with model"
                              value={target}
                              onChange={(e) => setTarget(e.target.value)}
                            >
                              {!enabled.length && (
                                <option value="">Choose a model</option>
                              )}
                              {enabled.map((m) => (
                                <option key={m.id} value={m.id}>
                                  {m.name}
                                </option>
                              ))}
                            </select>
                          </>
                        )}
                      </span>
                    </div>
                    {mention?.model && (
                      <div className="mention-recipient" role="status">
                        <MessageCircle size={16} /> Only {mention.model.name}{" "}
                        will receive this message
                        {squelched(mention.model.id) &&
                          " · currently squelched"}
                      </div>
                    )}
                    {mentionQuery !== null && (
                      <div
                        className="mention-suggestions"
                        aria-label="Choose a model"
                      >
                        {enabled
                          .filter(
                            (m) =>
                              m.name.toLowerCase().startsWith(mentionQuery) ||
                              m.id.toLowerCase().startsWith(mentionQuery),
                          )
                          .map((m) => (
                            <button
                              key={m.id}
                              type="button"
                              onClick={() => {
                                const duplicate =
                                  settings.models.filter(
                                    (p) =>
                                      p.name.toLowerCase() ===
                                      m.name.toLowerCase(),
                                  ).length > 1;
                                setDraft(`@${duplicate ? m.id : m.name} `);
                                document
                                  .querySelector(
                                    'textarea[aria-label="Message"]',
                                  )
                                  ?.focus();
                              }}
                            >
                              <Avatar
                                small
                                name={m.name}
                                provider={m.provider}
                              />
                              {m.name}
                              <small>@{m.id}</small>
                            </button>
                          ))}
                        {mentionQuery && (
                          <small>
                            Use a full model name or its @profile ID.
                          </small>
                        )}
                      </div>
                    )}
                    <textarea
                      aria-label="Message"
                      placeholder={
                        mode !== "direct"
                          ? mode === "broadcast"
                            ? "Who knows about this? Ask the group…"
                            : "Ask for independent opinions…"
                          : `Message ${enabled.find((m) => m.id === target)?.name || "a model"}`
                      }
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (
                          e.key === "Enter" &&
                          !e.shiftKey &&
                          !e.nativeEvent.isComposing &&
                          e.nativeEvent.keyCode !== 229
                        ) {
                          e.preventDefault();
                          if (!e.repeat) send();
                        }
                      }}
                    />
                    {images.length > 0 && (
                      <div className="attachment-preview">
                        {images.map((im, i) => (
                          <div key={i}>
                            <img src={im.preview} alt={im.name} />
                            <button
                              onClick={() =>
                                setImages(images.filter((_, j) => j !== i))
                              }
                              aria-label={"Remove " + im.name}
                            >
                              <X size={13} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="composer-bottom">
                      <div>
                        <input
                          ref={fileRef}
                          type="file"
                          accept="image/png,image/jpeg,image/webp"
                          multiple
                          hidden
                          onChange={attach}
                        />
                        <input
                          ref={projectFileRef}
                          type="file"
                          accept={ACCEPT}
                          multiple
                          hidden
                          onChange={addProjectFiles}
                        />
                        <IconButton
                          title="Add files to project (uploads folder)"
                          onClick={() => projectFileRef.current.click()}
                        >
                          <Plus size={18} />
                        </IconButton>
                        <IconButton
                          title="Attach images"
                          onClick={() => fileRef.current.click()}
                        >
                          <ImagePlus size={18} />
                        </IconButton>
                        <IconButton
                          title="Add code cell"
                          onClick={() => addCell()}
                        >
                          <SquareCode size={18} />
                        </IconButton>
                        <span className="compose-hint">
                          @model for one recipient · Enter to send
                        </span>
                      </div>
                      {active ? (
                        <button
                          className="stop-button"
                          onClick={() =>
                            api("/runs/" + active.id + "/cancel", "POST", {})
                              .then(() =>
                                setRuns(
                                  runs.map((r) => ({
                                    ...r,
                                    status:
                                      r.id === active.id
                                        ? "cancelled"
                                        : r.status,
                                  })),
                                ),
                              )
                              .catch(fail)
                          }
                        >
                          <Square size={13} />
                          Stop
                        </button>
                      ) : (
                        <button
                          className="primary"
                          disabled={
                            !draft.trim() ||
                            sending ||
                            !enabled.length ||
                            (cid && !conversationReady) ||
                            (mention
                              ? !mention.model ||
                                mention.empty ||
                                squelched(mention.model.id)
                              : mode !== "direct"
                                ? !recipients.length
                                : !enabled.some((m) => m.id === target) ||
                                  squelched(target))
                          }
                          onClick={send}
                        >
                          {sending
                            ? "Sending…"
                            : mention?.model
                              ? `Send to ${mention.model.name}`
                              : mode === "broadcast"
                                ? "Broadcast"
                                : "Send"}
                          <Send size={15} />
                        </button>
                      )}
                    </div>
                  </div>
                  <p className="saved-note">
                    {mode === "broadcast"
                      ? `Checks ${recipients.length} models for relevant knowledge. One answers first; others may pass. Knowledge checks also use model calls.`
                      : mode === "opinions"
                        ? `${recipients.length} models × ${discussionRounds} rounds. Each gives an independent opinion.`
                        : "Messages are saved automatically."}
                  </p>
                </div>
              </section>
              {participantsOpen && (
                <Participants
                  enabled={enabled}
                  settings={settings}
                  close={() => setParticipantsOpen(false)}
                  navigate={navigate}
                  broadcastTargets={broadcastTargets}
                  setBroadcastTargets={setBroadcastTargets}
                  toggleRecipient={toggleRecipient}
                  squelched={squelched}
                  toggleSquelch={toggleSquelch}
                  voiceBusy={voiceBusy}
                  conversationReady={conversationReady}
                  cid={cid}
                  simulated={simulated}
                  demo={demo}
                />
              )}
            </div>
          </>
        )}
      </main>
      {dialogs}
    </div>
  );
}
