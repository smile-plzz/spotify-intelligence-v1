# alfred-scratch — version-tracked home for everything Alfred & Master Bruce build together

> After first conversation: 2026-08-16

This repo is the canonical home for plans, logs, notes, and working scripts that
Alfred and Master Bruce have discussed, planned, or documented together — things
that don't belong in the focused project repos (`hermes-setup`, `spotify-taste-art-engine`,
`driver-psychology-analysis`, etc.) but still deserve version history.

## Why this exists

Master Bruce's home directory had a scattering of working files, logs, and markdown
documents — token dashboards, bot logs, session transcripts, system audit notes,
Instagram/Reddit automation scripts — that were version-tracked piecemeal (some in
their own repos, some in `smile-plzz/agent-scratch`, many not at all). This repo
consolidates them into one place with a clear structure, so anything we talk about
or build together has a permanent, searchable, versioned home.

## Structure

```
alfred-scratch/
├── logs/                  # Running logs: bot activity, session summaries, operations
│   ├── reddit-bot-log.md
│   ├── instagram-bot-log.md
│   ├── completion_notes.txt
│   └── conversations/
│       └── alfred-summary.md
├── dashboard/             # Token analytics & dashboard tooling
│   ├── token_dashboard.py
│   ├── test_dashboard.py
│   ├── edge_proxy.py
│   ├── alfred_relay.py
│   ├── public/            # Static dashboard UI files
│   └── api/               # Dashboard API endpoints
├── scripts/               # Utility scripts (profile readers, uploads, automation)
│   ├── read_profiles.py
│   ├── read_profiles2.py
│   ├── read_profiles3.py
│   ├── insta_uploader.py
│   └── inject_caption.js
├── docs/                  # Persistent documentation & plans
│   ├── workspace-dashboard.md   # README_raw.md / INDEX_raw.md → curated workspace index
│   ├── system-audit-2026-08-16.md
│   ├── recovery-checklist.md
│   ├── dashboard-activation.md
│   ├── power-handler.md
│   ├── claude-hub-integration.md
│   └── ... (any new plans or docs Alfred and Master Bruce produce)
├── projects/              # Meta-descriptions of projects that have their own repos
│   └── project-index.md   # Curated index of all active projects, their repos, status
├── .env.example            # Template for any secrets needed by scripts here
├── .gitignore
└── README.md
```

## What goes here vs. in a focused repo

| Goes here | Goes in its own repo |
|---|---|
| Running logs & session notes | Production code with its own CI/CD |
| Dashboard utilities & test scripts | Libraries/packages with dependencies |
| One-off automation scripts | Projects with their own docs, issues, releases |
| System audit & repair notes | Anything with external users or APIs |
| Cross-cutting plans & documentation | Anything Master Bruce wants to share publicly |

## Sync strategy

This repo lives on GitHub as `smile-plzz/hermes-alfred-scratch` (private). Local
working copies live at `C:\Users\ismai\alfred-scratch`. A periodic sync (cron or
manual `git push`) keeps the remote current. The repo is private — it may contain
logs, plans, and operational details Master Bruce doesn't want public.

## Adding new things

When Alfred and Master Bruce produce a new plan, log, or script that doesn't fit
any existing repo: put it here, commit, push. That's the whole rule. No ceremony.

---

*Alfred Pennyworth, 16 August 2026*
