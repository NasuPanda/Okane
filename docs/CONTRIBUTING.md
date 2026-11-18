# Contributing

## Branches and pull requests

- `main` is always demo-ready. Work on a branch: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`.
- Small PRs, one concern each. Describe what changed, how you tested it, and any new entry in
  `docs/ASSUMPTIONS.md`.
- CI must be green: ruff, pytest, frontend typecheck and build, and the forbidden-files check.
- Squash-merge with a clear message.

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
- Never paste real amounts, document numbers, user ids or names into code, tests, fixtures,
  issues, PRs or commit messages. Real-data tests assert aggregates only and skip in CI.
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
