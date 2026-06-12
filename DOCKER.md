# Publishing Quick Data to Docker Hub

This packages the app as two images — `quickdata-backend` (FastAPI + analysis
engine) and `quickdata-frontend` (Next.js) — so other devs can run the whole
thing with one command and no source checkout.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (you have Docker 29).
- A free [Docker Hub](https://hub.docker.com/) account.

## 1. Configure

Copy the env template and fill it in:

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```
GEMINI_API_KEY=your-key-here        # enables the chat agent (optional)
DOCKERHUB_USER=your-dockerhub-name  # your Docker Hub username
TAG=0.1.0                           # or latest
```

`docker compose` reads `.env` automatically. `.env` is git-ignored — never commit your key.

## 2. Log in

```powershell
docker login
```

## 3. Build the images

```powershell
docker compose build
```

This produces `DOCKERHUB_USER/quickdata-backend:TAG` and `…/quickdata-frontend:TAG`.

## 4. Test locally first

```powershell
docker compose up
```

Open **http://localhost:3000** (API at http://localhost:8020). `Ctrl+C`, then
`docker compose down` to stop.

## 5. Push to Docker Hub

```powershell
docker compose push
```

On a free account the repos are **public** (anyone can `docker pull`). For
private images, create the repos as private on Docker Hub first and add your
devs as collaborators (they must `docker login`).

### Multi-architecture (recommended for mixed teams)

The above builds for your machine's architecture only. If teammates are on Apple
Silicon **and** Intel/Windows, publish a multi-arch manifest with buildx:

```powershell
docker buildx create --use --name quickdata
docker buildx build --platform linux/amd64,linux/arm64 `
  -t $env:DOCKERHUB_USER/quickdata-backend:$env:TAG --push ./backend
docker buildx build --platform linux/amd64,linux/arm64 `
  --build-arg NEXT_PUBLIC_API_BASE=http://localhost:8020 `
  -t $env:DOCKERHUB_USER/quickdata-frontend:$env:TAG --push ./frontend
```

(Set the vars first, e.g. `$env:DOCKERHUB_USER="janedoe"; $env:TAG="0.1.0"`.)

## 6. Share with your devs

Send them **`docker-compose.hub.yml`** and these instructions:

```bash
# Each dev sets their own Gemini key and your Docker Hub username:
DOCKERHUB_USER=janedoe GEMINI_API_KEY=their-own-key \
  docker compose -f docker-compose.hub.yml up
```

On Windows PowerShell:

```powershell
$env:DOCKERHUB_USER="janedoe"; $env:GEMINI_API_KEY="their-own-key"
docker compose -f docker-compose.hub.yml up
```

Then open **http://localhost:3000**. They don't need the source — Docker pulls
both images. Each dev brings their **own** Gemini API key; the app runs without
one but the chat agent is disabled.

## Automated publishing (GitHub Actions)

[`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml)
builds and pushes **both** images (multi-arch: amd64 + arm64) to
`sidkid1978/quickdata-backend` and `…-frontend` whenever you push a version tag.

### One-time setup

1. Push this repo to GitHub (if you haven't):
   ```powershell
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
2. Create a Docker Hub **access token**: Docker Hub → Account Settings →
   Personal access tokens → Generate (Read & Write).
3. Add two repo secrets on GitHub (Settings → Secrets and variables → Actions),
   or via the CLI:
   ```powershell
   gh secret set DOCKERHUB_USERNAME --body "sidkid1978"
   gh secret set DOCKERHUB_TOKEN    --body "<your-access-token>"
   ```
   (`gh auth login` first if needed — this is the "github creds" step.)

### Cut a release

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The workflow publishes `sidkid1978/quickdata-backend:0.1.0` + `:latest` (and the
same for the frontend). You can also trigger it manually from the Actions tab
(workflow_dispatch). Watch progress with `gh run watch`.

## Notes & gotchas

- **Three images:** `quickdata-backend` (Quick Data API), `smart-dev-api` (Smart
  Dev API), and `quickdata-frontend` (the combined UI: `/` Data, `/dev` Dev).
- **Analyzing your own code in the Dev section:** the Smart Dev container can only
  see paths inside itself. Compose mounts a workspace read-only at `/workspace`
  (defaults to this repo; override with `PROJECTS_DIR=/path/to/code`). In the
  `/dev` UI, analyze `/workspace` (or a subfolder). `rollback_changes` can plan
  but not execute against a read-only mount.



- **The frontend's API URL is baked at build time.** `NEXT_PUBLIC_API_BASE` is
  inlined into the JS bundle (`http://localhost:8020`), which is correct when
  running via compose on a laptop. If you deploy the frontend to a real host,
  rebuild it with the public backend URL:
  `--build-arg NEXT_PUBLIC_API_BASE=https://api.example.com`.
- **CORS** already allows any `localhost` port, so the default compose setup
  works out of the box.
- **Sample data** ships inside the backend image at `/app/data`
  (`QUICKDATA_DATA_DIR`); users can also upload their own files in the UI.
- **New version?** Bump `TAG`, then `docker compose build && docker compose push`.
