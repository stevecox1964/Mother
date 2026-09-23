# Mother

A local app for discussing a software project with your configured models. Broadcast asks who has relevant knowledge, then lets an informed model answer first and peers add useful findings. Direct chat and independent opinions are also available. Conversations and selected project context are saved locally.

## Run

On Windows, double-click **Start-Mother.cmd**, or run `./Start-Mother.ps1` in PowerShell. Requires Python 3.11+ and Node.js 20.19+ or 22.12+. The launcher installs dependencies, builds the React app, starts a hidden local server, and opens [Mother](http://127.0.0.1:5010).

The app is local-only, listening on `127.0.0.1:5010`. There is no Slack, Docker requirement, hosted database, account system, or external orchestration service. To run the server in a terminal instead:

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

Use Ctrl+C to stop a foreground server. For a server started by the launcher, its PID is saved in `data/server.pid`; verify that process before stopping it. Running the launcher again stops any Mother server started from this folder, then starts a new one with the current code. If another program uses the port, the launcher stops with an error; close that program or set `MOTHER_PORT`. `server.log` and `server-error.log` contain startup and error information.

## First conversation

**Mother — Main project** is the built-in home for developing Mother itself. It points to this application's repository and has its own models and conversations. **Mother architecture** opens its project context, including the architecture proposal and saved review. Both documents are initially selected for the Mother project's model context. New unrelated projects start without these documents. The main project opens by default on first use; subsequent project selections are remembered. Existing **Default project** conversations stay in their original project.

The sidebar is a project tree. Each project expands to show **Chat** with its conversations, plus **Models**, **Files**, **Setup**, **Search** and **Trash** for that project. **System setup** at the bottom covers every project on this machine. Use **Projects → +** to create a project. Choose **Coding**, **Research**, **Writing**, or **General**. Each project gets its own model configuration, workspace folder, saved conversation stack, search results, and Trash. New projects copy the current project's model profiles once and start with no selected files or conversations. Credentials remain shared locally, so you can reuse your provider connections. Switch projects by clicking another project in the tree; Mother remembers the last project and conversation in this browser. The pencil beside the open project edits its name and type. Click the open project's arrow to fold it without switching projects. The trash icon beside **Projects** lists deleted projects.

Existing conversations and settings are assigned to **Default project** automatically. Running replies continue in their original project when you switch projects. **Models & souls** and **Project context** apply to the selected project; message routing always uses the conversation's owning project.

1. Open **Models & souls**. The starter profiles are examples, not verified account entitlements. Enter the exact model IDs your accounts support and save credentials. Credentials are write-only in the UI, stored in `data/.env`; process environment variables are also supported. Reference-project credentials are not imported.
2. Add, remove, enable, or disable profiles. Connections are machine-wide in **System setup**; each project chooses which of them to use under its own **Models**. Different profiles can use the same vendor or even the same model with different souls. Choose an enabled model as the default chat model. **Save configuration** applies edits to future messages.
3. In **Project context**, select the relevant source files. In **Models & souls**, set each model's **Expertise & knowledge**, context access, and **Files for this model**. Existing profiles retain access to all selected files when code access is enabled; you can choose a different subset for each model. Expertise describes knowledge; it does not load files or create persistent model memory. Source findings posted to the shared board are visible to peers.
4. Open **Chat**. **Broadcast** checks who knows about the question; **Independent opinions** asks everyone for an answer; **Direct** asks one model. Press Enter to send; Shift+Enter adds a new line.

The **Try simulated chat** button disables existing profiles and adds three explicitly labeled demo profiles. It calls no external API for those profiles. Re-enable your real profiles and select a real default model when finished with the demo.

Each conversation has a three-dot menu for **Rename**, **Export transcript**, and **Delete**. Delete moves it to **Trash** and removes it from the sidebar and search. Restore it from Trash at any time; its messages and attachments remain on disk. Stop an active reply before deleting its conversation.

The trash icon beside the open project deletes it. Deleting a project removes it from the sidebar; its folder, settings and conversations stay on disk. Restore it from **Projects → Deleted projects**. **Mother** and **Default project** cannot be deleted, and a project with a running reply cannot be deleted until the reply finishes.

**Files** shows the project folder as a tree. Click a file to see it; the page cannot edit files. It lists the text files that models can read (no credential files, files over 200 KB, or folders such as `node_modules`), plus images (PNG, JPEG, GIF, WebP) and PDFs up to 8 MB. Models cannot read images or PDFs. To add files, type a folder (or leave it empty for the top of the project) and click the upload icon. Uploads follow the same rules. If a file already exists, Mother replaces it and keeps the old version in `data/backups`. In a conversation, the **+** icon below the message box uploads files to the project's `uploads` folder with the same rules, then adds an "Uploaded to project: …" line to your message so models know the files are there. Use the refresh icon after a model writes new files.

The chat scrolls down with new messages only while you are at the bottom, so you can read older messages during a reply.

## Chat behavior

**Broadcast** starts with one structured knowledge check per unsquelched recipient. Models offer specific relevant knowledge or pass; these checks are recorded in the audit, not posted as chat answers. Source claims must include an exact excerpt that matches a file actually supplied to that model. Mother prioritizes matching source excerpts, then self-assessed relevance and declared expertise; ties use profile order, not response speed, vendor, or the default model. This is a routing estimate, not proof of answer quality or of an excerpt's relevance. The board explains why the first speaker was chosen.

The selected speaker answers first. By default, other models that offered knowledge review sequentially, seeing all accepted additions, and may post only a new finding, correction, alternative, or answer to a specific question. Passes stay silent. Exact duplicate text is suppressed; semantic novelty otherwise depends on the model following the review instructions. Choose **Find a speaker + answer** to skip review, or **Additions + optional answer update** to let the first speaker make a final delta only when peers added something. There is no permanent chief. Selection happens again for every broadcast. A failed or squelched first speaker falls back to another valid offer. If everyone passes or fails, Mother reports that no available model offered an answer rather than inventing consensus.

Knowledge checks use model calls too, capped at the smaller of the profile limit and 4,096 output tokens, without tools. An N-model broadcast uses at most N checks, one answer attempt per candidate (normally one total), one review per remaining candidate, and optionally one update. Reviews and answers can use the bounded model tools described below. Invalid or truncated structured responses are withheld with an error; they are never published as ordinary answers. **Independent opinions** preserves the earlier parallel 1–3-round discussion, and **Direct** produces one reply. Every mode uses bounded recent shared conversation history.

Per-model **Squelch** persists for the conversation, prevents subsequent participation and discards pending output without blocking peers. Unsquelching permits a new knowledge check on the next broadcast; it does not revive a discarded offer. Existing provider requests may still finish and incur charges. **Stop** cancels further stages and discards late responses.

The API defaults to `mode: "direct"` for compatibility; an empty target list selects the default model. `mode: "broadcast"` uses knowledge discovery, while `mode: "opinions"` requests independent responses. Group modes accept a recipient subset or all enabled unsquelched models. `rounds: 1|2|3` chooses discussion depth; direct mode always uses one reply. Existing `chief_id` is only the direct-chat default. Historical discussions remain in the archive.

Provider calls have a configurable output token cap and a 120-second read timeout. There are no automatic retries or background model activity while idle. Stop discards in-flight output; it cannot undo a request already received or billed by a provider.

Every run records the model configuration, souls, context-file hashes, target selection, per-response provider/model IDs, elapsed time, and available token usage. Changes to configuration do not alter the identity or soul used by a running discussion.

PNG, JPEG, and WebP inputs are supported (up to two images, 4 MB each). Images are sent only to participants with image input enabled. That switch declares the model's capability; a provider may reject a model that does not actually support images. Only the current user message's images are sent; older images remain attached to the archive but are not automatically resent. Audio and video are future work.

## Storage and memory

```text
data/
  config.json                       # Default project's model/context configuration
  .env                              # credentials; never returned through settings
  mother.db                         # authoritative SQLite conversations/events/runs
  conversations/YYYY/MM/DD/<id>.jsonl
  attachments/<id>                  # original image bytes
  projects/<project-id>/
    config.json                     # this project's independent model/context configuration
    workspace/                      # empty working folder created with the project
    conversations/YYYY/MM/DD/<id>.jsonl
    attachments/<id>
```

Project names, types, and conversation ownership are stored in SQLite. Default project's original config, attachments, and conversation mirrors keep their existing locations for compatibility. New projects use the folders above. Project IDs keep folder names stable when a project is renamed. The workspace is created empty; **Project context** can point to an existing source folder instead.

`GET/POST /api/projects` lists or creates projects; `PUT /api/projects/<id>` changes a name or type. `DELETE /api/projects/<id>` hides a project, `GET /api/projects/deleted` lists hidden projects, and `POST /api/projects/<id>/restore` brings one back. `GET /api/files?project_id=<id>` lists the project folder's text files, images and PDFs. `GET /api/files/content?project_id=<id>&path=<rel>` returns one text file, `GET /api/files/raw?project_id=<id>&path=<rel>` returns one image or PDF, and `POST /api/files/upload?project_id=<id>` with JSON `{path, base64}` saves one file; the **Files** page in each project uses them. Settings, model catalogs, conversation lists/creation, search, and Trash accept `?project_id=<id>` (omitting it selects Default project). Conversation operations resolve the owning project and reject a mismatched explicit project ID. Search indexing uses one shared local worker, with results and progress counts filtered to the selected project.

**Code cells** sit in the chat between messages. Add one with the code icon in the composer, or click **Make cell** on a Python block in a model reply. Code runs only when you click Run (or press Shift+Enter) in one Jupyter kernel per conversation, with the project folder as the working folder. Text, errors and images (for example `plt.show()`) show under the cell. Click the cell header to collapse or open it. The header **Run all** icon restarts the kernel and runs every cell top to bottom; it stops at the first error and marks later cells as skipped. **Stop** interrupts running code; if Windows cannot interrupt it within 5 seconds, Mother kills the kernel and its variables are lost. Models read each cell's code and text output in the chat history, and vision models also get up to two images from cells run since the last message. Cell code and outputs live in SQLite, not in the JSONL mirrors. Routes: `POST /api/conversations/<id>/cells`, `PUT`/`DELETE /api/cells/<id>`, `POST /api/cells/<id>/run`, `POST /api/conversations/<id>/cells/run-all`, `POST /api/conversations/<id>/cells/stop`.

Messages are persisted automatically with UTC millisecond timestamps and an ordered sequence number. SQLite runs in WAL mode. JSONL mirrors are rebuilt atomically per conversation/day after each event and repaired from SQLite at startup. SQLite is the source of truth, so a interrupted mirror write cannot erase the conversation. For large archives, an incremental export worker would avoid rewriting a full conversation/day per event.

**Search conversations** combines SQLite FTS5 word matches with local vector similarity through `sqlite-vec`. **Smart search** ranks both kinds of matches, including related wording; **Exact text** keeps literal substring search. Both honor UTC date filters and exclude Trash. Clicking a result opens its conversation. Searches return up to 200 messages, with the best matching chunk shown for a semantic result.

The local embedding model is `nomic-embed-text:v1.5` (768 dimensions), served by Ollama at `127.0.0.1:11434`. On a new installation, start Ollama and run `ollama pull nomic-embed-text:v1.5` once. The model is already installed on this machine. No conversations are sent to a cloud embedding provider. Search indexing generates vectors only; it does not produce chat replies.

Old messages are queued on startup, and new user/model messages are queued when saved. A single background worker indexes overlapping text chunks and commits each message's vectors atomically in `data/mother.db`. Jobs survive restarts, completed messages are not repeatedly embedded, and failed indexing pauses until **Retry indexing** is selected. Exact text search remains available while Ollama is unavailable. Messages in Trash retain their vectors but are excluded before nearest-neighbor selection; Restore makes them searchable again.

`GET /api/search/hybrid?q=...&mode=hybrid` returns results, a fallback warning when needed, and index progress. `mode=keyword` uses literal text; both accept `start`, `end`, and `conversation_id`. `GET /api/search/status` reports progress; `POST /api/search/index` resumes pending/failed indexing. Legacy `GET /api/search` remains a text-search array endpoint.

Each conversation exports as JSONL or a readable timestamped text file. Models receive bounded recent conversation history (80,000 characters) and selected source files. Vector search indexes saved message text; it does not yet index source repositories, image contents, or automatically inject unrelated archived conversations into chat context.

To back up, stop Mother and copy `data/`, including credentials if desired. Do not commit that directory. Credentials are plaintext on your local disk and protected by your OS account, not a vault. This initial version is for one local user; it intentionally rejects non-local hosts and cross-origin browser writes.

## Development and verification

The React + Vite frontend and Flask + SQLite backend follow BookMarkManager's structure. Provider profiles and credential utilities are extracted from Unreal Sim. See [docs/REUSE.md](docs/REUSE.md) for exact provenance and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and next steps.

```powershell
# Backend tests (no external calls)
.\.venv\Scripts\python.exe -m pytest -q

# Frontend build
cd frontend
npm.cmd run build

# Development UI (keep backend running separately)
npm.cmd run dev
```

The dev UI uses port 5174 and proxies `/api` to port 5010. Built assets are served by Flask. `MOTHER_PORT` changes the production port; adjust the Vite proxy if using a different backend port for development. `MOTHER_DATA_DIR` selects a different data directory. Run one server process per data directory because mirror/config writes and restart recovery assume one owner.

## Model tools

Models with tools enabled can use:

- **Files:** `list_files`, `read_file` and `search_files` read text files in `/project` and the shared read-only `/tools` and `/docs` folders.
- **Writing:** `write_file`, `edit_file` and `delete_file` create, change and delete UTF-8 text files, only inside the project folder. Set **Setup → Model access to the project folder** to read/write to allow them. A write must pass the file's current `sha256`, so a model cannot overwrite a change it has not read. Mother saves each replaced or deleted file under `backups/` in project storage. Shared folders, `data/`, `.git`, credential files and binary files cannot be written.
- **Web:** `web_search` and `web_fetch` use the [Browserbase](https://www.browserbase.com/) Search and Fetch APIs. They appear only after a key is saved in **System setup → Web tools**. Pages are limited to 50,000 characters and are treated as untrusted data. Browserbase requests are billed to your Browserbase account.
- **Settings:** `get_model_settings` and `list_provider_models` read Mother settings (credentials excluded) and provider model catalogs.

Turn tools off for a whole project on the **Setup** page, or for one model on the **Models** page. One reply can make at most 12 provider requests and 40 tool calls. File reads and web pages share the context character limit.

Web content can contain text written to mislead a model. Consider turning off web tools for models that have write access.

## Deliberate first-version boundary

Mother is a working discussion and coding harness. Models can read and write project files, but they cannot execute shell commands or programs. Coding workers, isolated Git worktrees, patch review, interactive browser sessions, targeted peer tool calls, archive retrieval tools, streaming tokens, and richer multimodal inputs belong in the next stage.

## License

MIT. See [LICENSE](LICENSE).
