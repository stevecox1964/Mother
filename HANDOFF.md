# Mother handoff

Updated September 9, 2026. This replaces the older single-reply-only handoff.

## Start here

- September 10 update: projects now have independent configurations and conversation stacks. The built-in `mother` project (**Mother — Main project**) is specifically for this application's development, linked to this repository. Existing `default` conversations have not been moved. See `docs/MOTHER_ARCHITECTURE_REVIEW.md` for the review of `MOTHER_KNOWLEDGE_MODEL_ARCHITECTURE.md` and implementation sequence; the broad architecture is still a roadmap.

- Workspace: `C:\Users\user\Desktop\Mother`
- App: **http://127.0.0.1:5010/** (local to this computer)
- Health was checked while writing this handoff: `{"name":"Mother","status":"ok","version":"0.1.0"}`.
- The knowledge-broadcast implementation is running. Refresh existing browser tabs for the current frontend.
- The next requirement is **shared project knowledge that models can learn from**. It was discussed after broadcast was implemented, but **has not been built**.
- No implementation agent or background coding task is working on that requirement. This turn only updates this handoff.

## Navigation (September 11, 2026)

The sidebar is a project tree. **Projects** lists every project; the selected one is expanded and the others are collapsed. Clicking a collapsed project switches to it, which is blocked while a reply is running.

Under the open project: **Chat** (with its saved conversations nested beneath it and a `+` to start one), **Models**, **Setup**, **Search** and **Trash**. **System setup** sits alone at the bottom because it covers every project on this machine.

The former per-model sidebar entries and the `view: "chat"` direct-message screen were removed. Use the **Direct** mode button or an `@model` mention in the composer to reach one model. The **Mother architecture** shortcut now lives on the Mother project's Setup page, not the sidebar.

## System model registry and project names (September 11, 2026)

Renames and deletions in **System setup** now reach every project.

- Deleting a connection in System setup removes it from every project's model list. A browser tab opened before the deletion still cannot put it back; that save is rejected with "System model no longer exists."
- A project profile stores `name_alias`. While it is empty the project shows the registry name, so a system rename propagates. Typing a different name in **Name in this project** sets the alias and pins that project's name.
- `SystemConfig.save_system` writes the registry, then carries renames and deletions into every project config. The route `PUT /api/system/settings` calls it instead of saving the registry alone.
- `SystemConfig.adopt_registry_names` runs once at startup for configs written before `name_alias` existed. Those names were copies made by the registry migration, not deliberate aliases, so they adopt the registry name. Where two profiles in one project share a connection (several souls on one model) the distinct name is kept as a real alias. It writes `config.pre-names.json` beside each config it changes.

Live data was repaired on September 11: the Mother and Default projects had stale names (`Claude Fable 5.1` for `Fable`, `Local thinker` for `Qwen`, `Claude Opus 5` for `Opus`, and so on) and a `custodian` profile bound to a connection that no longer existed. Backups are `data/config.pre-names.json` and `data/projects/mother/config.pre-names.json`.

## User intent and preferences

Mother is a simple, local, multi-vendor harness for software-project conversations. The user wants OpenAI and Claude models to collaborate using different knowledge and file context. OpenRouter was explicitly deferred.

The critical correction was that broadcasting the same question to everyone produced repetitive answers. The user clarified: **“The broadcast is, who knows about this?”** Models with relevant context should speak, and models with nothing new should pass. A fixed lead or favored vendor is inappropriate: a different model may know more about each question. Preserve the user's ability to squelch individual models while discussion continues.

The latest requirement, in the user's words: **“If a certain model comes back with ‘truth’. The other models get to learn this.”** This is the next feature to address. The assistant acknowledged it but made no code changes for persistent shared knowledge.

Keep the dark Slack-like UI, ordinary local URL, Enter-to-send / Shift+Enter-for-newline behavior, saved conversations, and concise communication. Avoid repeated permission requests for ordinary authorized implementation work. Preserve user data and settings.

## What works now

### Knowledge broadcast

Broadcast is the default UI mode. For each message:

1. Unsquelched recipients perform concurrent structured knowledge checks. They offer relevant knowledge or pass; this stage does not publish an answer from every model.
2. Claims of source evidence must include an exact excerpt matching a file actually supplied to that model. Mother prioritizes matching excerpts, then self-assessed relevance, then declared expertise. Ties use configured profile order, never response speed or the default model.
3. A provisional speaker answers first. The board explains the selection and can show its supporting excerpts.
4. With the default depth, other models that offered knowledge review sequentially. Each sees the first answer and earlier accepted additions. They may contribute a new finding, correction, substantive alternative, or answer to an unresolved question, or pass silently.
5. The optional deepest setting lets the first speaker update its answer only if peers contributed. That update may also pass.

There is no permanent chief. Selection starts again on every broadcast. A failed or squelched first speaker can fall back to another valid offer. Failed speakers are not retried as reviewers. If nobody offers a usable answer, Mother says so rather than asking every model to produce a full answer.

Discussion depth options are:

- **Find a speaker + answer**: discovery and one answer, without reviews.
- **Answer + useful additions**: discovery, first answer, optional peer contributions (default).
- **Additions + optional answer update**: also permits a conditional update from the first speaker.

Knowledge checks incur provider calls. They have no tools and use at most the smaller of the profile cap and 4,096 output tokens. Answers and reviews may use the existing bounded read-only model tools. Checks and silent passes retain usage/audit metadata as hidden `run` events. Invalid or truncated structured responses are withheld with a visible error, not treated as ordinary answers.

Exact duplicate contributions are suppressed after normalization. Semantic novelty still depends on model compliance. A matching excerpt proves access to that source text; it does **not** prove the model's conclusion is correct or the excerpt is relevant. Routing is an estimate, not a quality verdict or truth-verification system.

### Other interaction modes and controls

- **Independent opinions** preserves parallel independent answers and optional discussion over 1–3 rounds.
- **Direct** sends to one selected model and produces one visible answer.
- `chief_id` only sets the default direct-chat model.
- **Squelch** is per model, per conversation. It prevents later participation and discards pending output without holding up other models. Unsquelching does not revive an old discarded offer; the next broadcast can check that model again.
- **Stop** prevents further stages and discards late responses. Already-sent provider calls may still finish and incur charges.

### Per-model expertise and files

In **Models & souls**, profiles have **Expertise & knowledge**, **Context access**, and **Files for this model**.

- First choose the overall source set in **Project context**.
- `context_mode: "board"` provides shared conversation context without source files.
- `context_mode: "files"` provides the assigned subset of globally selected files.
- Profile `context_files: null` preserves the previous all-selected-files behavior; a list restricts access, and `[]` assigns none. Paths not globally selected are not sent.
- `expertise` describes a model's specialty. It does not load files or create memory. Existing profiles were not automatically assigned invented expertise.
- Source content is read once and distributed per profile. Audit manifests retain path/hash/size per model, without raw file bodies. Models can learn source findings that peers post to the shared conversation.

### Existing foundation

Conversations are saved in SQLite with dated JSONL mirrors. Rename, transcript export, Trash/Restore, image inputs, and project-file context are available. Keyword and local vector search use FTS5, sqlite-vec, and Ollama `nomic-embed-text:v1.5` at port 11434. Failed indexing can be retried; exact text search remains available.

Models see bounded recent conversation history (80,000 characters). Sequential reviewers see earlier peer contributions in the same conversation. Search does not automatically inject unrelated archived conversations, index repository source, or maintain shared project facts.

Read-only model tools can inspect settings and query provider catalogs. Credentials are excluded from snapshots. Each tool-enabled completion allows at most two tool rounds, eight tool executions, and three generation requests; a whole broadcast includes several completions. Models cannot change settings, write project files, execute shell commands, or apply patches.

## Next requirement: shared project knowledge

**Not implemented:** an explicit, durable, project-scoped knowledge store that all models consult across conversations.

Today, “learning from peers” means seeing their messages in bounded shared conversation history. There is no fact promotion, evidence lifecycle, project-wide fact retrieval, contradiction handling, or invalidation when a cited file changes. Do not tell the user those capabilities already exist.

The previous assistant proposed the following direction; the user has not separately confirmed every design detail:

- Share supported findings automatically across conversations belonging to the same project.
- Retain the finding, evidence, originating model, source event, and file version/hash.
- Keep unsupported claims tentative and disagreements visible.
- Reconsider findings when source files change or contradictory evidence appears.
- Learning means supplying saved knowledge as model context, not retraining model weights.

Suggested implementation sequence for the next coding task:

1. Establish stable project identity and associate conversations/findings with it. Current project context is a global setting; do not accidentally share facts between unrelated projects when it changes.
2. Add persistent records for claims, supporting evidence, provenance, status, and superseding/contradicting findings. Distinguish supported, tentative, disputed, and stale information without equating confidence or model agreement with truth.
3. Capture useful findings from accepted contributions through a bounded process. Preserve source evidence and attribution; avoid saving every sentence as a fact or silently promoting unsupported assertions.
4. Retrieve a bounded set of relevant project findings for discovery, answers, reviews, and future conversations. Keep original source-file permissions meaningful: shared findings are visible to peers, but that does not grant unrestricted access to another model's source files.
5. Add a clear UI for inspecting evidence, correcting or disputing a finding, and seeing why it is stale. File changes should flag affected findings for reconsideration.
6. Test cross-model and cross-conversation reuse, restart persistence, project isolation, conflicting claims, changed source hashes, correction propagation, and retrieval/context limits.

These are implementation recommendations, not claims of completed work. Continue to preserve direct chat, independent opinions, squelch, cancellation, and existing conversation storage.

## Live configuration observed at handoff

The public settings API currently reports these enabled profiles as ready:

| Name | Provider | Configured model ID | Profile ID |
| --- | --- | --- | --- |
| Astra | OpenAI | `gpt-6-astra` | `chief` |
| Claude Fable 5.1 | Anthropic | `claude-fable-5-1` | `critic` |
| Claude Opus 5 | Anthropic | `claude-opus-5` | `model-1788655096656` |
| Claude Sonnet 5 | Anthropic | `claude-sonnet-5` | `model-1788655112389` |
| Claude Haiku 4.5 | Anthropic | `claude-haiku-4-5-20251001` | `model-1788655134090` |

All five enabled profiles currently have **board-only context and no declared expertise**. Three files are selected globally, but none of these enabled profiles receives source files until code access is enabled. This matters when assessing whether knowledge routing can favor real file context. The implementation added configuration controls but did not change these user settings.

“Ready” means configuration/credential checks passed, not a guarantee of provider availability or model capabilities. Read current settings before making changes; the user can edit them. Do not copy credential values into handoffs, logs, prompts, or commits.

## Main implementation files

| File | Responsibility |
| --- | --- |
| `backend/mother/collaboration.py` | Knowledge protocol, parsing, matching excerpts, speaker selection, ordered reviews, fallback |
| `backend/mother/ensemble.py` | Prompt construction, provider calls, phase handling, bounded history, audits, publication |
| `backend/mother/workspace.py` | Safe source selection, snapshots, per-model file distribution |
| `backend/mother/config.py` | Profiles, expertise/file assignment validation, settings and credentials |
| `backend/mother/system_config.py` | Machine-wide model registry, project bindings, name propagation and deletion pruning |
| `backend/mother/app.py` | Flask API, mode/target validation, snapshot capture, conversation and search routes |
| `backend/mother/store.py` | SQLite conversations/events/runs, participation revisions, atomic squelch/publication, mirrors |
| `backend/mother/providers.py` | Provider adapters, structured demo behavior, bounded tool loop |
| `backend/mother/model_tools.py` | Redacted settings, provider catalogs, read-only tool runtime |
| `backend/mother/tool_protocol.py` | Native provider tool declarations and continuations |
| `backend/mother/search.py` | Search schema, embedding jobs, hybrid retrieval |
| `frontend/src/main.jsx` | Entry point only; mounts `ProjectApp` |
| `frontend/src/components/App.jsx` | Chat board: modes, depth controls, speaker explanations, live status, composer |
| `frontend/src/components/Sidebar.jsx` | Project tree navigation: each project opens to Chat, conversations, Models, Setup, Search, Trash |
| `frontend/src/components/Participants.jsx` | Recipients panel: broadcast selection, squelch, project context summary |
| `frontend/src/components/ConversationDialogs.jsx` | `useConversationActions` hook: row menu, rename, trash and new-conversation dialogs |
| `frontend/src/components/ProjectApp.jsx` | Project selection and creation |
| `frontend/src/components/ProjectModels.jsx`, `ModelSettings.jsx` | Per-project model list; model editor (souls, expertise, files) |
| `frontend/src/components/SystemSetup.jsx` | Machine-wide model registry and shared folders |
| `frontend/src/components/ProjectSettings.jsx`, `Archive.jsx`, `Post.jsx`, `ui.jsx` | Project folder/context, search, message rendering, shared widgets |
| `frontend/src/style.css` | Dark interface, routing and assignment layout |
| `tests/test_collaboration.py` | New knowledge-broadcast behavior and edge cases |
| `tests/test_broadcast.py` | Earlier group behavior, now exercised primarily through independent opinions |

`POST /api/conversations/<cid>/messages` accepts `mode: "direct" | "broadcast" | "opinions"`, `targets`, and `rounds: 1|2|3`. The API defaults to direct for compatibility; the UI defaults to broadcast. An empty group target list selects enabled unsquelched models; an empty direct target list selects the default. Direct always uses one reply.

Other useful endpoints: `/api/health`, `/api/settings`, `/api/conversations/<cid>`, `/api/conversations/<cid>/models/<mid>/squelch`, `/api/runs/<rid>/cancel`, `/api/search/hybrid`, and `/api/search/status`. Mutating requests require JSON. Squelch uses PUT and cancel uses POST.

## Validation evidence

Completed during the preceding implementation turn, not rerun for this documentation-only update:

- Full backend suite: **82 passed**.
- After preventing failed first speakers from being retried as reviewers: all **10 collaboration tests passed** again.
- Ruff unused-name checks passed, and the production frontend build passed.
- Tests cover source-backed nondefault speaker selection, per-model file isolation, concurrent discovery, silent passes, duplicate suppression, sequential review context, malformed responses, fallback, Stop, and in-flight squelch.
- Live OpenAI/Anthropic check used a synthetic `nav.py` in isolated temporary storage. OpenAI passed without source context; Anthropic gave the single visible answer from its assigned file. Existing user conversations and settings were untouched.
- A separate live Anthropic discovery check returned an exact matching source excerpt. This does not establish that every future structured response will comply.
- Browser checks confirmed mode/depth controls, the expertise field, file assignment UI, and the updated “Who knows about this?” heading. The checked page had no captured browser console errors.
- Production health was checked again while writing this handoff and is OK. No paid model checks or test suite were repeated for the handoff.

Older `docs/VALIDATION.md` and portions of `docs/ARCHITECTURE.md` describe the earlier single-reply implementation. Use this handoff, current code, and README for current behavior.

## Run, build, and restart

From the workspace root in PowerShell:

```powershell
# Build frontend, then refresh the browser.
npm.cmd --prefix frontend run build

# Automated tests; no live provider calls.
.\.venv\Scripts\python.exe -m pytest -q

# Python checks.
.\.venv\Scripts\python.exe -m ruff check --select F backend/mother tests

# Foreground server, only when another instance is not already running.
.\.venv\Scripts\python.exe backend\run.py
```

Double-click `Start-Mother.cmd` to launch. The launcher builds and starts a hidden local server when stopped. When Mother is already running, it opens the app and exits without rebuilding or restarting it.

For backend changes, check for active runs, resolve the port-5010 listener, and verify its command line belongs to this workspace before stopping it. `data/server.pid` can refer to a launcher whose child owns the listener; do not treat an old PID as a permanent restart target. Start replacement background servers with a hidden window. Logs are `server.log` and `server-error.log`.

Run one backend per data directory. `MOTHER_DATA_DIR` selects isolated storage and `MOTHER_PORT` changes the server port. The Vite development server uses 5174 and proxies API requests to 5010. Keep synthetic verification messages out of live user conversations.

## Storage and repository precautions

- Preserve `data/`: SQLite database, conversation mirrors, attachments, config, and credentials.
- All top-level source/documentation entries currently appear **untracked** in Git. No commit or PR has been created. Untracked files are the working project, not disposable scratch files.
- Credentials live in `data/.env` or process environment variables. Never print or commit them.
- Models receive only supplied source files according to context settings; excerpts posted to the shared board are available to peers.
- Mother owns reused copies from BookMarkManager and Unreal Sim; there is no runtime dependency on those reference checkouts. See `docs/REUSE.md` for provenance.
- Shell execution, autonomous coding workers, patch review/application, streaming, richer media inputs, and persistent shared project knowledge remain outside the current implementation.
