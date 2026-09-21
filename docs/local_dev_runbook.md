# Local Dev Runbook

Quick reference for running the backend locally while the production
Render deployment is unavailable. This is a personal cheat sheet, not
project documentation — see
[docs/email_feature_handoff.md](email_feature_handoff.md) for the
actual architecture and context.

## Start everything

```bash
# 1. Open Docker Desktop (Start menu) and wait for it to fully start.

# 2. Start the backend container
cd backend
docker compose up -d

# 3. Start the tunnel (leave this running in its own terminal window,
#    or background it with & in Git Bash)
"/c/Users/LENOVO/AppData/Local/Microsoft/WinGet/Packages/Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe/ngrok.exe" http 8000
```

## Verify it's working

```bash
curl http://localhost:8000/health
curl https://basket-parrot-cleaver.ngrok-free.dev/health
```
Both should return `{"status":"healthy"}`.

**If the tunnel gives you a different URL than the one above**, the free
ngrok URL changed on restart. Update
`CONFIG.ENVIRONMENTS.test.BACKEND_URL` in the Gmail Apps Script project
to match, or `processInbox` will fail with a 404.

## Check status without restarting anything

```bash
docker info >/dev/null 2>&1 && echo "Docker: up" || echo "Docker: down"
curl -s -o /dev/null -w "Backend: %{http_code}\n" http://localhost:8000/health
curl -s -o /dev/null -w "Tunnel: %{http_code}\n" https://basket-parrot-cleaver.ngrok-free.dev/health
```

## Check recent activity / errors

```bash
cd backend
docker compose logs --tail 100
docker compose logs --tail 200 | grep -iE "error|exception"
```

## Stop everything

```bash
cd backend
docker compose down
taskkill //IM ngrok.exe //F
```

## Where credentials live

`backend/.env` and `backend/app/.env` (both git-ignored, kept in sync
manually — a pre-existing bug in one backend service makes the second
copy necessary for local runs, see the handoff doc). Fill in real values
for `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`, `SUPABASE_URL`,
`SUPABASE_KEY`, `SHEETS_WEBHOOK_URL`, `SHEETS_SECRET`, and
`EMAIL_WEBHOOK_SECRET` (the last one also has to match
`CONFIG.BACKEND_SECRET` in the Apps Script).

## Things worth checking when something isn't classifying

1. Is the Anthropic API key's account out of credits? Check
   `docker compose logs` for `credit balance is too low`.
2. Is Docker/the tunnel actually up (see Verify section above)?
3. Does the Apps Script's `CONFIG.ENVIRONMENTS.test.BACKEND_URL` still
   match the current tunnel URL?
4. Is the email actually labeled with the Apps Script's input label?
   Unlabeled mail is never touched, by design.
