# Hosted demo

Decision and limits: `docs/ASSUMPTIONS.md` A41 (issue #67).

| Link | What it runs | Status |
|---|---|---|
| Cloudflare Worker (`okane.<account>.workers.dev`) | The UI on the synthetic `fixtures/*.json` ("Practice data"), no backend | Main link for now |
| Oracle Always Free VM | The full app with Ollama, on synthetic data, behind basic auth | Planned |

**Synthetic data only, on every host.** The app has no login. Never upload a real workbook to a
hosted copy, and never build the hosted UI from anything other than the committed fixtures.

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
