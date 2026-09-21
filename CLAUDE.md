# Project notes for Claude

This is MCL Patr (mcl-daak) — a municipal document digitization system.
`backend/` is a FastAPI service, `frontend/` a React/Vite app.

## Before working on the email classification feature

Read [docs/email_feature_handoff.md](docs/email_feature_handoff.md)
first. It covers the architecture, key design decisions and their
rationale, current implementation state, active blockers, and planned
next work for the Gmail-based grievance classification feature. That
work currently lives on the `feature/aarushi-email-grievance-classification`
branch, not yet merged to `main`.

For day-to-day local dev commands (starting/stopping the backend and
tunnel), see [docs/local_dev_runbook.md](docs/local_dev_runbook.md).

## General conventions in this repo

- Commit at natural checkpoints during implementation work — several
  focused commits, not one large commit at the end.
- Keep commit messages short and in plain language; avoid long
  multi-paragraph commit bodies.
- Never commit real credentials — `backend/.env` and `backend/app/.env`
  are git-ignored and must stay that way.
