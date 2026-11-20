# Contributing

## Branches and pull requests

- `main` is always demo-ready. Work on a branch: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`.
- Small PRs, one concern each. Describe what changed, how you tested it, and any new entry in
  `docs/ASSUMPTIONS.md`.
- CI must be green: ruff, pytest, frontend typecheck and build, and the forbidden-files check.
- Merge with a merge commit (not squash or rebase), so each PR's commits stay reviewable one
  by one, then delete the branch.
- When `main` moves on, merge `main` into your branch; don't rebase a branch others have seen.
  Resolve conflicts in `fixtures/`, `openapi.json` and `schema.d.ts` by rerunning
  `make fixtures` / `make types`, never by hand. Then rerun `make test`: when a merged change
  moves a figure a test asserts (a count or a median), confirm which findings changed before
  updating it.

## Before you push

```bash
make lint
make test
```

If you changed a pydantic model or an endpoint: `make types` and commit the regenerated
`frontend/src/api/schema.d.ts` and `openapi.json`. If you changed an engine or the generator:
`make fixtures` and commit `fixtures/`.

## Data rules (non-negotiable)

- Never commit a spreadsheet, a DuckDB file, `.env`, anything under `data/` except `.gitkeep`,
  or anything under `docs/reference/`. CI blocks these, but do not rely on it.
- Real row-level values (amounts, document numbers, user ids) may appear in Git only where
  the brief quotes them as an Expected value or an open-item candidate, and only in
  `docs/BRIEF.md`, `docs/ASSUMPTIONS.md` and the `test_real_*` golden tests. Cite the brief
  section or ASSUMPTIONS item next to each one (decision A35).
- Never put real values in fixtures, the generator, engine or UI code, prompts, logs, issues,
  PRs or commit messages, and never commit a full row, a name or a `NAME###` value. Synthetic
  data uses invented user ids, not ones the brief quotes. Entity and account codes (C192,
  279006) are structural and allowed everywhere.
- Real-data tests skip in CI and never print row-level data.
- `fixtures/` is generated from synthetic data by `make fixtures`; never hand-edit it with real
  values.

## Engine changes

- Engines are pure: lines and `Rules` in, records out. No I/O, no clock, no literals for
  thresholds: add a field to `Rules`.
- Every engine change needs a unit test in `test_engines.py`, a synthetic assertion in
  `test_golden.py`, and, if the brief gives an Expected value, a real-data golden test.
- Unspecified behaviour: implement the simplest version, mark `# ASSUMPTION:` in code, and add
  or update an item in `docs/ASSUMPTIONS.md` with an owner line.

## UI language

Write for accountants: open item, accrual, payment, exposure, expected by. No model or ML
jargon, no unexplained scores. Label amounts "scaled".

## Tutorial mode (A39)

- When you add, move or rename a section the tutorial explains, keep its `data-tour="key"`
  marker, or update `frontend/src/tutorial/steps.tsx` in the same pull request. A new page or
  section gets a card there, in plain words.
- The tutorial stays read-only: no API call that writes, and no clicks or typing on the page.
  Figures on its cards come from the data on screen, never typed into the script.
