# Deploying EAIOS live

The repo ships a single-container web build (`Dockerfile.web`): the React OS
shell, FastAPI API, and WebSocket all served from **one process, one port,
one URL** — no CORS, no reverse proxy needed. `render.yaml` deploys it to
Render's free tier in a few clicks.

## Path A — Render.com free tier (recommended)

Prereqs: repo published on GitHub (GitHub Desktop → Publish repository).

1. **Get a free LLM key (2 min)** — sign up at https://console.groq.com →
   API Keys → Create. Copy the `gsk_…` key. (Skip this and the site runs on
   the deterministic mock LLM — still fully demoable.)
2. **Create the service** — https://render.com → sign in with GitHub →
   **New → Blueprint** → select your EAIOS repo → Render reads `render.yaml`
   → **Apply**. First build takes ~5–8 min (npm build + pip install).
3. **Add the key** — service → **Environment** → `OPENAI_API_KEY` → paste the
   Groq key → Save (triggers a quick restart).
4. **Open it** — `https://eaios.onrender.com` (or similar). Log in with
   `admin@eaios.dev / admin12345`. The health chip should read **Live**, and
   Admin → Models shows `groq / llama-3.1-8b-instant`.

Free-tier behavior (say this in the viva, it sounds intentional — it is):
- **Sleeps after ~15 min idle**; the next visitor waits ~1 min for cold start.
  Wake it before a demo by opening the URL early.
- **Ephemeral disk**: SQLite + uploads reset on every deploy/restart.
  `SEED_ON_START=1` re-seeds the demo corpus automatically, so the site is
  always in a clean, demoable state.
- WebSockets (presence, live agent feed) work on Render free.

### Custom domain (optional)
Service → Settings → Custom Domains → add `eaios.yourdomain.com`, create the
CNAME it shows, TLS is automatic.

## Path B — Hugging Face Spaces (free, AI-community visibility)

1. https://huggingface.co/new-space → SDK: **Docker** → create.
2. Push the repo to the Space (or upload), add a `Dockerfile` that is just
   `Dockerfile.web`'s content, and set Space secrets `OPENAI_API_KEY`,
   `OPENAI_BASE_URL=https://api.groq.com/openai/v1`,
   `OPENAI_MODEL=llama-3.1-8b-instant`, `SECRET_KEY=<random>`.
3. Spaces expose port 7860: set `PORT=7860` as a Space variable.

## Path C — any Docker host / VPS

```bash
docker build -f Dockerfile.web -t eaios-web .
docker run -d -p 80:8000 \
  -e SECRET_KEY=$(openssl rand -hex 32) \
  -e OPENAI_API_KEY=gsk_... \
  -e OPENAI_BASE_URL=https://api.groq.com/openai/v1 \
  -e OPENAI_MODEL=llama-3.1-8b-instant \
  -v eaios-data:/app  \
  eaios-web
```
The named volume keeps SQLite + uploads across restarts.

## Path D — Kubernetes (production story)

`deploy/helm/eaios` — HPA, Qdrant StatefulSet, TLS ingress, nightly backups:
```bash
helm upgrade --install eaios deploy/helm/eaios -n eaios --create-namespace \
  --set ingress.host=eaios.yourdomain.com
```
CI can do this for you: push to GitHub → Actions → **CI → Run workflow**
(after adding a `KUBE_CONFIG` secret). See `.github/workflows/ci.yml`.

## Troubleshooting

- **Health shows `mock`** → `OPENAI_API_KEY` missing/typo'd, or
  `LLM_PROVIDER` isn't `auto`/`openai`.
- **Groq 429s** → free tier is ~30 req/min; EAIOS degrades to mock per-call
  (`safe_complete`) instead of erroring, so demos never break.
- **First request after idle is slow** → free-tier cold start; open the URL
  a minute before presenting.

## Connectors — Google Drive / Gmail OAuth

The Connectors app ingests external data into the knowledge base. The **Sample
Workspace** provider works out of the box (bundled demo data, no setup). To
connect **real** Google Drive / Gmail you supply an OAuth *access token*; the
providers then call the Drive API v3 (`files.list` + export Docs as text) and
the Gmail API (recent message snippets).

Getting a token for a demo (fastest):

1. Open the [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/).
2. In *Step 1*, authorize the scopes
   `https://www.googleapis.com/auth/drive.readonly` and
   `https://www.googleapis.com/auth/gmail.readonly`.
3. *Step 2* → **Exchange authorization code for tokens** → copy the **Access
   token**.
4. Paste it into the Google Drive / Gmail card in the Connectors app and hit
   **Connect & sync**.

Access tokens expire in ~1 hour — fine for a live demo. For a production
consent flow, register an OAuth client in Google Cloud Console (APIs &
Services → Credentials), add your deployed URL to the authorized redirect
URIs, request the read-only scopes, and store the refresh token server-side.
EAIOS never stores the token: it's used only for the single sync request.
