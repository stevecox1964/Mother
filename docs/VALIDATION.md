# Validation · 2026-09-05

## Current model settings and discovery update

- `python -m pytest -q`: **60 tests passed**. Includes existing chat, conversation actions, SQLite/FTS/vector search and cancellation coverage, plus provider catalogs, auth headers, pagination/deduplication, malformed responses, redaction, tool allowlists, saved connection selection, per-turn caching, tool budgets, native continuation formats, aggregate usage, one visible reply, and disabled-tool behavior.
- `ruff check --select F backend/mother tests`: passed.
- `npm run build`: passed.
- Live catalog GETs succeeded with the saved connections: OpenAI returned 129 model IDs, Anthropic 11, and Ollama 4 installed models.
- Live OpenAI and Anthropic generation checks both invoked `get_model_settings` and `list_provider_models` and returned the Anthropic catalog count. OpenAI used three generation requests and Anthropic two, with one final answer each. These standalone checks did not add test messages to the user's conversations.
- Browser walkthrough on the running app: Models & souls → Anthropic → Fetch models loaded 11 options. Selecting `claude-fable-5` populated Model ID; the original ID was restored locally and no configuration was saved during verification. The final layout and accessible input names were inspected.
- The local server was restarted after confirming no active runs. Health and live catalog API checks passed at `http://127.0.0.1:5010`.
- Gemini and compatible endpoints were tested with HTTP fixtures; live catalog and tool calls for those providers remain unverified. Ollama catalog discovery was verified live; native Ollama tool continuations were tested with fixtures.

Credentials were not printed, included in tool results, or added to test transcripts. Existing user settings and conversation data were preserved.

## Adding more Anthropic models

- The add button now follows the selected provider, reuses its connection and credential reference, and supports catalog discovery before a new profile is saved. Choosing a catalog entry names the new chat model automatically.
- Production frontend build passed. The new flow was exercised in the browser to add the user-requested latest Opus, Sonnet and Haiku models alongside existing Fable 5.1, using Anthropic's live model catalog and creation dates. Configuration save succeeded; all four Anthropic entries were verified enabled and ready through the API and present in the chat model selector.
- Existing Fable's generic “Anthropic” label was renamed “Claude Fable 5.1”. The default model and existing conversation contents were preserved. No generation test messages were added.
