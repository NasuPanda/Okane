# Hosted demo

Decision and limits: `docs/ASSUMPTIONS.md` A41 (issue #67).

| Link | What it runs | Status |
|---|---|---|
| Cloudflare Pages (`<project>.pages.dev`) | The UI on the synthetic `fixtures/*.json` ("Practice data"), no backend | Main link for now |
| Oracle Always Free VM | The full app with Ollama, on synthetic data, behind basic auth | Planned |

**Synthetic data only, on every host.** The app has no login. Never upload a real workbook to a
hosted copy, and never build the hosted UI from anything other than the committed fixtures.

## Cloudflare Pages (practice-data UI)

Set up once in the Cloudflare dashboard: **Workers & Pages → Create → Pages → Connect to Git**,
pick this repository, then:

| Setting | Value |
|---|---|
| Production branch | `main` |
| Framework preset | None |
| Root directory | `frontend` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Environment variable | `VITE_API_MODE` = `fixtures` |
| Environment variable | `NODE_VERSION` = `22` (Vite 7 needs Node 20.19 or later) |

Pages clones the whole repository, so the `@fixtures` alias (`../fixtures`) resolves during the
build. With no `404.html` in the output, Pages serves `index.html` for any path, so the
`/exposure`, `/sentinel` and `/rules` links work when opened directly.

- **Redeploy:** every push to `main` deploys. Every other branch gets a preview link
  (`<branch>.<project>.pages.dev`), useful to check a branch before merging.
- **Keep the fixtures current:** after a change to `backend/app/schemas.py`, an engine or the
  fixture client (`frontend/src/api/client.ts`), run `make fixtures` and commit the result.
  A run with no other change only moves run ids, timestamps and file hashes.
- **Try it locally first:**
  `cd frontend && VITE_API_MODE=fixtures npm run build && npx vite preview`

### Check after a deploy

1. The header reads "Practice data".
2. Open `/`, `/exposure`, `/sentinel` and `/rules` directly and reload each one. None should
   return 404.
3. The browser's network tab shows no `/api/` requests.
4. Run a tutorial, make a decision and change a rule. They work, and reset on reload.
