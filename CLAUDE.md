# Project notes for Claude

This is MCL Patr (mcl-daak) — a municipal document digitization system.
`backend/` is a FastAPI service, `frontend/` a React/Vite app.

## Start here

Read [docs/context_handoff.md](docs/context_handoff.md) first. It is the
single project context document: architecture, both pipelines (scanned
documents and the Gmail email channel), data model, the Apps Script
projects, operating notes and known follow-ups. Keep it updated when the
project changes instead of adding new context files.

## General conventions in this repo

- Commit at natural checkpoints during implementation work — several
  focused commits, not one large commit at the end.
- Keep commit messages short and in plain language; avoid long
  multi-paragraph commit bodies.
- Do not add `Co-Authored-By` or "Generated with Claude Code" attribution
  lines to commits or pull requests.
- Never commit real credentials — `backend/.env` and `backend/app/.env`
  are git-ignored and must stay that way.
