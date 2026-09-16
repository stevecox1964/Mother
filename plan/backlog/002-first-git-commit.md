# 002 — Get this project into git

**Priority:** P2
**Status:** open
**Added:** 2026-09-11
**Closed:** _Not yet._

## Why

`C:\Users\user\Desktop\Mother` is a git repository with **zero commits**. `git log` reports "your current branch 'master' does not have any commits yet". All 61 source and documentation files are untracked. There is no history, no way to see what a session changed, and no way to undo a bad change except by hand.

The user's words on 2026-09-11: "right now it's too messed up to bother". The tree has since been cleaned up, so the objection is weaker than it was, but this stays deferred until the user says go.

Three sessions of work by different models now sit in this tree with no commit boundary between them. The longer that continues, the less a first commit can tell anyone.

## What "done" looks like

- A first commit exists on a branch, containing the backend, frontend, tests, docs and launcher scripts.
- `git status --short` is clean apart from files that are meant to be ignored.
- No credentials, database, conversation archive, attachment, build output or dependency directory is tracked.
- `git log` shows at least one commit with a message that says what the project is.
- The user has confirmed the branch name. `master` is the current branch; the configured main branch for pull requests is `main`, so these disagree and the user must pick.

## Where to start

- `.gitignore` already exists at the repo root and covers `.venv/`, `node_modules/`, `frontend/dist/`, `data/`, `.env`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `*.log` and `artifacts/`. Verify it before the first `git add`.
- Confirm the exclusions really hold: `git check-ignore -v data/.env` should report the `data/` rule. `git status --porcelain --untracked-files=all | wc -l` was 61 on 2026-09-11.
- Sizes to keep out: `frontend/node_modules` is 92 MB, `.venv` is 66 MB, `data` is 12 MB, `artifacts` is 3.6 MB.
- Decide whether `plan/` (this backlog and future handoffs) is tracked. The `handoff` skill says not to commit handoffs automatically.
- Ask the user before creating a remote. There is none configured.

## Watch out for

- **`data/.env` holds live provider credentials.** It is ignored today. Check again immediately before the first `git add`, and never use `git add -f` anywhere under `data/`.
- **`data/` is the working application state**, not scratch: the SQLite database, conversation mirrors, attachments and per-project configuration. Ignoring it is correct; deleting it is not.
- **Untracked does not mean disposable.** Every top-level entry in this tree is real work.
- **Do not commit or push without being asked.** The user has to choose the branch name and whether a remote exists.
- Two stray files exist at the repo root from a previous run: `server.log` and `server-error.log`. Both match the `*.log` ignore rule. `data/server.pid` is covered by `data/`.
