# Hosted demo

Decision and limits: `docs/ASSUMPTIONS.md` A41 (issue #67).

| Link | What it runs | Status |
|---|---|---|
| Render free web service (`https://okane.onrender.com`, basic auth) | The full app on the built-in synthetic sample, template comments | Main link |
| Cloudflare Worker (`okane.<account>.workers.dev`) | The UI on the synthetic `fixtures/*.json` ("Practice data"), no backend | Backup link, always on |

**Synthetic data only, on every host.** The app has no login. Never upload a real workbook to a
hosted copy, never copy `data/` to a server, and never build the hosted UI from anything other
than the committed fixtures. The basic auth password goes in the submission, never in Git.

## Render (full app)

Render builds `Dockerfile.demo` from the repository. Its last stage, `render`, runs two programs
in one container:

- **Okane** on `127.0.0.1:8001`. The synthetic sample workbooks and sample rates are baked into
  the image, so every run reads them unless someone uploads a file. The analysis date is the
  extract date, as with `make demo`, so the figures can differ from the Cloudflare backup (pinned
  to 18 Nov 2026).
- **Caddy** on `:10000`, Render's default port. It asks for the basic auth password on
  everything except `/api/health`. Render adds HTTPS in front.

What the free tier gives and costs:

- **No card**, and 512 MB with a tenth of a CPU. Measured locally under the same limits: the
  health check answers after about 15 s, the first run finishes after about 35 s, and memory
  stays near 105 MB.
- **It sleeps after 15 minutes without visits** and takes about a minute to wake. The uptime
  check below keeps it awake. Render's 750 free hours a month cover one service around the
  clock, so don't add a second free service.
- **The disk resets** on every restart, redeploy or settings change. Decisions, rule changes and
  uploads start over, and a fresh run rebuilds the Inbox from the sample in about 35 s.
- **No AI on the host.** Comments are the labelled template, unless the app is pointed at a
  laptop's Ollama (see "AI comments for a recording" below).

### Set up once

1. **Password hash.** Pick a password, then run
   `docker run --rm caddy:2.11.9 caddy hash-password --plaintext 'the-password'`. Keep the output
   for step 3.
2. **Service.** At render.com, sign in with GitHub, then **New → Web Service**. Connect GitHub,
   grant access to this repository only, pick it, and fill in:

   | Field | Value |
   |---|---|
   | Name | `okane` (gives `okane.onrender.com` if it is free) |
   | Language | Docker |
   | Branch | `main` |
   | Region | Frankfurt (EU Central) |
   | Root directory | empty |
   | Dockerfile path | `./Dockerfile.demo` |
   | Docker build context | `.` |
   | Instance type | Free |
   | Health check path (Advanced) | `/api/health` |
   | Auto-deploy | On commit |

3. **Environment variables** (the same page, or Settings → Environment later):

   | Key | Value |
   |---|---|
   | `OKANE_AUTH_USER` | `okane` |
   | `OKANE_AUTH_HASH` | the hash from step 1, pasted as is, **without quotes** |

4. **Deploy.** The first build takes a few minutes. Render finds port 10000 on its own.
5. **Keep it awake.** At UptimeRobot (free; or cron-job.org), add an HTTP monitor for
   `https://okane.onrender.com/api/health` every 5 to 10 minutes. This page needs no password and
   answers only `{"status":"ok"}`.

### Redeploy and reset

- **Redeploy:** every push to `main` deploys, and the run starts again on the sample.
- **Reset to the start state** (after visitors made decisions or uploaded something): in the
  Render dashboard, restart the service (or **Manual Deploy → Deploy latest commit**). Either
  one starts from an empty disk.
- **Change the password:** replace `OKANE_AUTH_HASH`. The service restarts with the new hash.

### AI comments for a recording (optional)

The app reaches Ollama with no login, so the only AI it can use without a code change is an
Ollama we run. On recording day, a laptop's Ollama can serve the hosted app:

1. On the laptop: `ollama serve`, with `qwen2.5:7b-instruct` pulled.
2. On the laptop: `cloudflared tunnel --url http://localhost:11434 --http-host-header="localhost:11434"`.
   It prints a `https://<random>.trycloudflare.com` address.
3. In Render, set `OKANE_OLLAMA_URL` to that address. The service restarts, its first run drafts
   the top three comments, and others are drafted when opened.
4. Afterwards, stop the tunnel and delete `OKANE_OLLAMA_URL`. Anyone who knows the address can
   use the laptop's Ollama while the tunnel runs, and the address changes on every restart.

### Check after a deploy

1. Without a password, `/` returns 401 and `/api/health` returns 200.
2. With the password, the header shows a synthetic run, and the Inbox lists the sample findings.
3. `/exposure`, `/sentinel` and `/rules` open directly and on reload.
4. A finding's comment shows the labelled template (or a checked AI draft while a tunnel is set).
5. Run "Check now": the run status updates live, without a page reload.

### Try it locally first

```sh
docker build -f Dockerfile.demo -t okane-render .
docker run --rm -m 512m --cpus 0.1 -p 10000:10000 \
  -e OKANE_AUTH_USER=okane -e OKANE_AUTH_HASH='<hash>' okane-render
```

Then open `http://localhost:10000`. The limits match Render's free instance. Locally the hash
needs the single quotes, because the shell would otherwise read its `$` signs.

## Any Docker VM (full app with Ollama, optional)

`deploy/compose.yaml` runs the same app with Ollama and Caddy on any Docker host with about 8 GB
of memory: a VM with a card-backed free tier, or a spare machine. Unlike Render, it keeps its
disk and serves AI comments. It was written for an Oracle Always Free VM, which we could not
sign up for.

- **okane** builds the `app` stage of `Dockerfile.demo`. Runs draft no comments
  (`OKANE_AI_PREDRAFT_TOP=0`), because a new draft takes minutes on CPU. Decisions, rule
  changes and the comment cache live in the `okane-data` volume.
- **ollama** keeps `qwen2.5:7b-instruct` in memory. It publishes no port.
- **caddy** serves HTTPS with Let's Encrypt for every name in `OKANE_HOSTNAMES` (for example a
  free DuckDNS name plus `<ip-with-dashes>.sslip.io`), with basic auth.

Steps, once the host has Docker and ports 80 and 443 open:

1. Clone the repository. It is private, so use a read-only deploy key.
2. Run `cp deploy/.env.example deploy/.env`. Fill in the hostnames, the user and the hash (keep
   the hash in single quotes).
3. Start Ollama, pull the model, then start the rest:
   ```sh
   cd deploy
   docker compose up -d ollama
   docker compose exec ollama ollama pull qwen2.5:7b-instruct
   docker compose up -d --build
   ```
4. Draft every comment once. Run this inside `tmux`. It prints progress only, never comment
   text; each line should read `model passed`. It took about 2 minutes in total on an
   Apple-silicon laptop, and takes much longer on a small VM.
   ```sh
   docker compose exec -T okane python - <<'EOF'
   import httpx
   c = httpx.Client(base_url="http://localhost:8000", timeout=1200)
   ids = [e["id"] for e in c.get("/api/exceptions").json()]
   for n, i in enumerate(ids, 1):
       r = c.post(f"/api/exceptions/{i}/comment").json()
       print(f"{n}/{len(ids)}", r["source"], r["verifier"])
   c.post("/api/runs", params={"wait": True}).raise_for_status()  # the Inbox picks up the cache
   print("run done")
   EOF
   ```
- **Redeploy:** `git pull && cd deploy && docker compose up -d --build okane`. If prompts or
  findings changed, rerun step 4.
- **Reset:** stop and remove `okane`, remove the `okane_okane-data` volume, start `okane` again,
  and rerun step 4.
- **Locally:** set `OKANE_HOSTNAMES=localhost`, then open `https://localhost` and accept Caddy's
  local certificate. `docker compose down -v` removes the test volumes afterwards.

## Cloudflare (practice-data UI)

The dashboard no longer offers Pages, so the UI is a Worker that only serves static assets.
`frontend/wrangler.jsonc` points it at `dist/` and sends unknown paths to `index.html`
(`not_found_handling: single-page-application`), so the `/exposure`, `/sentinel` and `/rules`
links work when opened directly.

Set up once in the Cloudflare dashboard: **Workers & Pages → Create application → Import a
repository**, connect GitHub (grant access to this repository only), pick it, then:

| Field | Value |
|---|---|
| Project name | `okane` (must equal `name` in `frontend/wrangler.jsonc`) |
| Build command | `npm run build` |
| Deploy command | `npx wrangler deploy` (default) |
| Non-production branch deploy command | `npx wrangler versions upload` (default) |
| Path | `frontend` |
| API token | Let Cloudflare create one (default) |
| Variable | `VITE_API_MODE` = `fixtures` |
| Variable | `NODE_VERSION` = `22` (Vite 7 needs Node 20.19 or later) |

Both variables are build variables: Vite bakes `VITE_API_MODE` into the bundle, so the Worker
needs no runtime variables. After creating it, check **Settings → Build**: the production branch
is `main`, and both variables are listed. The build clones the whole repository, so the
`@fixtures` alias (`../fixtures`) resolves.

- **Redeploy:** every push to `main` deploys. Other branches upload a preview version with its
  own preview URL (shown on the build and on the pull request), useful to check a branch before
  merging.
- **Keep the fixtures current:** after a change to `backend/app/schemas.py`, an engine or the
  fixture client (`frontend/src/api/client.ts`), run `make fixtures` and commit the result.
  A run with no other change only moves run ids, timestamps and file hashes.
- **Try it locally first:**
  `cd frontend && VITE_API_MODE=fixtures npm run build && npx wrangler dev` (serves `dist/` with the
  same not-found rule as the hosted copy)

### Check after a deploy

1. The header reads "Practice data".
2. Open `/`, `/exposure`, `/sentinel` and `/rules` directly and reload each one. None should
   return 404.
3. The browser's network tab shows no `/api/` requests.
4. Run a tutorial, make a decision and change a rule. They work, and reset on reload.
