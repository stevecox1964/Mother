# Design

Mother is a local chat app. A model profile separates its display name, provider, model ID, instructions, and context access. One user message produces one visible reply from one selected model; no automatic discussion rounds, peer replies, or chief synthesis follow it.

The React app sends a single model target to the Flask API. If omitted, the API selects the configured default (stored as `chief_id` for compatibility), falling back to the first enabled model. Multiple targets are rejected. Legacy `rounds` settings are ignored by the runner.

The runner snapshots configuration and selected source files, records a hidden run event, and calls the selected provider. Ordinary chat needs one generation request; read-only tool use allows at most two continuation rounds, eight tool executions and three generation requests. A successful response adds one reply; a provider failure adds one error without a retry. Completion updates the run status without inserting a chat message. Stop discards in-flight output. The server marks interrupted runs after restart.

Each message has an author, type, conversation, UTC timestamp, sequence, and metadata. SQLite is authoritative and dated JSONL files mirror its events. The selected model sees bounded recent conversation history and source files only when its context access permits them. Switching models preserves conversation context; it does not create private histories. Historical discussion messages remain readable.

## Model introspection and discovery

`model_tools.py` exposes two read-only operations: `get_model_settings` and `list_provider_models`. The runner supplies an allowlisted settings snapshot with secret values redacted, and optional tools for profile instructions and live catalogs. Tools can only use canonical provider endpoints or saved profile connections; model arguments cannot supply arbitrary URLs, headers, credentials, or settings mutations. Keys are used by HTTP adapters and excluded from tool results. Only a small audit of tool name/provider/success and aggregate token usage is recorded with the final reply.

`tool_protocol.py` translates native OpenAI Responses, Anthropic, Gemini, Ollama and compatible chat tool calls. Continuations preserve reasoning blocks, call IDs and Gemini thought signatures. Calls are bounded and cancellation-aware; duplicate catalogs within a turn are cached. Intermediate model prose and tool results are not posted as chat events. Profiles can disable native tools without losing the settings snapshot.

The settings picker calls `GET /api/providers/<provider>/models?profile_id=<saved-id>`. Catalog requests use saved connections, do not send conversation text, do not follow redirects, and return normalized IDs/names with a timestamp and partial-list flag. Pagination is bounded to ten pages, 2,000 entries, and a 45-second between-request deadline (each HTTP request has its own timeout). Model lists do not prove compatibility with this chat adapter.

## Search storage and execution

SQLite remains authoritative. `message_fts` is an FTS5 index; `message_chunks` maps overlapping chunks to events; `message_vectors` is a sqlite-vec `vec0` table with 768-dimensional cosine vectors. Its active flag, UTC day, and conversation ID allow filtering before KNN selection. `indexed_events` records content hashes and the fixed model/chunking signature. Search-model changes require an explicit derived-index migration; incompatible signatures are rejected rather than mixing vector spaces.

A database trigger inserts text and a durable embedding job with each searchable event. Startup backfills old messages. `SearchService` runs one indexing worker, makes local Ollama embedding requests outside database locks, and atomically stores each complete event's chunks/vectors. It does not automatically retry failed jobs. Search uses reciprocal-rank fusion for exact substring, FTS5 word, and vector matches, deduplicates by event, and falls back to text if embeddings are unavailable. The query-vector cache is bounded to 64 queries. At most 200 vector chunk neighbors are considered per query before grouping them into messages; heavily chunked messages can reduce result diversity at large scale.

Trash and Restore update vector visibility in the same transaction as the conversation flag. Existing transcript/mirror data remains intact. Vector/text indexes live in the same database and are included in SQLite backups. Startup enables the worker only in the server entry point; application-factory tests do not contact an embedding service unless explicitly requested.

## Next coding layer

The next useful increment is an explicit task/patch protocol over this board:

1. The chief proposes bounded work items, ownership, expected files, and acceptance criteria.
2. A coding participant receives an isolated Git worktree and a restricted file/command tool adapter. Provider-specific function calling maps onto the same harness tools.
3. Changes are attached to the board as patches with test results and a base commit. Peers review those artifacts.
4. Mother checks the patch against the current base, exposes a diff for human review, and applies an accepted change through one serialized integration path.

This prevents concurrent models from silently overwriting the same working directory. Before enabling execution, add a run budget, cancellation-aware process management, tool-call auditing, and a concrete approval policy for changes that need it.

Other increments: targeted `ask_peer` requests with bounded depth; models querying archived discussions and source indexes; file-scoped retrieval for large projects; session-specific participant rosters; persistent background workers for resume; streaming text; audio/video adapters. The current server marks interrupted runs explicitly after restart rather than pretending it can resume partially billed provider calls.
