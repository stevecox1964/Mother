# Reuse inventory

Reference projects were inspected read-only. Mother owns its copies and does not import from live source-project paths at runtime.

The Unreal path in the request did not exist. The matching active project was found at:

`C:\Users\user\Documents\Unreal Projects\AAAAAA_Unreal_SIM\unreal-sim\Python`

The second reference is:

`C:\Users\user\Desktop\React\BookMarkManager`

| Source | Mother destination | Treatment |
| --- | --- | --- |
| Unreal `agent_runtime/config_store.py` | `backend/mother/reused/config_store.py` | Copied unchanged. Used for comment-preserving credential writes and secret-variable detection. Mother validates names/values and resolves credentials with dotenv without interpolation. |
| Unreal `agent_runtime/provider_profiles.py` | `backend/mother/reused/provider_profiles.py` | Copied unchanged. Mother uses its seed profiles and JSON writer; replaces simulation-specific decision/vision roles with configurable participants and chief assignment. |
| Unreal `agent_runtime/llm_router.py`, `_openai_text` and `_anthropic_call` | `backend/mother/providers.py` | Adapted HTTP request/extraction shapes into a per-profile adapter. Removes global provider selection, world prompts, movement actions, and model-specific thinking defaults. Reports provider failures as board events. |
| Unreal `agent_runtime/ollama_adapter.py`, `chat` and `strip_think` | `backend/mother/providers.py` | Extracted native chat payload, explicit thinking control, image support and defensive thinking-tag stripping. Replaced the global host and Unreal overlay/VRAM state with profile configuration and a five-minute keep-alive. |
| Unreal `agent_runtime/agent.py` | `backend/mother/config.py`, `ensemble.py` | Studied identity/goals/rules separation; adapted the idea to per-profile soul text. Did not copy the Unreal agent class or world-rule loader. |
| Bookmark `frontend/src/utils/saveToFile.js` | Same relative frontend path | Copied unchanged; used by the board's readable transcript export. |
| Bookmark `frontend/vite.config.js`, `package.json` | Mother frontend equivalents | Adapted React/Vite setup and relative API proxy, moved to ports 5174/5010, added Markdown and icon components. |
| Bookmark `backend/app/__init__.py` | `backend/mother/app.py` | Adapted single-process API + built-SPA serving. Removed permissive CORS and added local host/origin checks. |
| Bookmark `backend/app/database.py`, `models.py` | `backend/mother/store.py` | Reused the Flask/SQLite storage approach; implemented a new append-only event schema for cross-model conversations, runs, sequence numbers and dated JSONL mirrors. No video tables. The later search extension adds sqlite-vec using the reference database loader and vector-table approach. |
| Bookmark `brain_providers/base.py`, `openai_provider.py` | `backend/mother/providers.py` | Reused the provider boundary and OpenAI Responses approach. Did not import remote brain publishing, vector-store uploads or video-specific RAG. |

The provider HTTP interfaces were checked against official API documentation:

- [OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Gemini generateContent](https://ai.google.dev/api/generate-content)
- [Ollama chat](https://docs.ollama.com/api/chat)

Anthropic's request and extraction behavior was adapted from the working Unreal integration. All adapters were validated with mocked HTTP fixtures. Live OpenAI and Anthropic generation/tool checks and OpenAI, Anthropic and Ollama catalog lookups succeeded. Gemini and compatible endpoint live behavior remains unverified. See [VALIDATION.md](VALIDATION.md).

No `.env` files, credentials, databases, transcripts, world state, generated assets, or reference-project dependencies were copied. BookMarkManager declares MIT in its README. Unreal's copied code is retained for the user's local project; licensing for any external distribution has not been assessed.

## SQLite vector search

BookMarkManager `backend/app/database.py` and `backend/app/embedding_service.py` are the concrete references for `backend/mother/search.py`: load sqlite-vec on each connection, disable extension loading immediately afterward, persist overlapping text chunks with vectors, and return the best chunk per source message. Mother adapts the 2,000-character/200-character-overlap chunking strategy.

Mother uses the local Ollama `nomic-embed-text:v1.5` model with 768-dimensional vectors instead of the reference project's Gemini embedding API. Its inputs use `search_document:` and `search_query:` task prefixes. No reference-project credentials, transcripts, or databases are imported. Model files were downloaded through the official Ollama model library.

Mother adds FTS5 word search, reciprocal-rank fusion, durable incremental indexing jobs, atomic event-level writes, validation of complete finite embedding batches, a bounded query-vector cache, and Trash/date/conversation filtering inside vector KNN queries. The single-reply chat runner is unchanged by search indexing.

Verified interfaces: [sqlite-vec Python](https://alexgarcia.xyz/sqlite-vec/python.html), [vec0 metadata filtering](https://alexgarcia.xyz/sqlite-vec/features/vec0.html), [Ollama embed API](https://docs.ollama.com/api/embed), and [nomic-embed-text](https://ollama.com/library/nomic-embed-text).
