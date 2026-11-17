# Okane

Nokia Finance Hackathon 2026 (Budapest) project.

## Project structure

- [ ] To be updated!

```
.
├── .env.example        # template for local env vars (copy to .env)
├── .gitignore
├── README.md
├── data
│   ├── interim/        # intermediate outputs (git-ignored)
│   └── processed/      # final outputs (git-ignored)
└── docs
    └── NOTE.md         # working notes
```

## Local files (not in git)

These are git-ignored and must be obtained separately:

| Path | Contents | Why ignored |
|---|---|---|
| `data/raw/*.xlsx` | Hackathon datasets | Confidential: hackathon use only, do not share outside the event |
| `docs/reference/` | Kickoff slides, our notes with dataset figures, etc. | Mentor contact details; figures taken from the confidential data |
| `.env` | Local secrets | Secrets |

After cloning, place the three `Hackathon_*_Nokia.xlsx` files in `data/raw/`.
