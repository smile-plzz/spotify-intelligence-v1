# Index

One line per project — read this first, then open only the `STATUS.md` you actually need. Every
edit here gets committed/pushed automatically like anything else in this repo — what's *not*
automatic is the table content itself: it only changes when a session updates it by hand after a
project's state changes materially.

| Project | Last activity | State | Needs attention? |
|---|---|---|---|
| [TimeCapsule](repos/TimeCapsule/STATUS.md) | 2026-08-05 | **UI prototype on main** (React/Vite/TS + sample data). Any-Day/heatmap/search/collections/compare demoable. ZIP parser not wired (`jszip` unused). Audits 01–08 + in-repo `STATUS`/`CHANGELOG`/`docs/TRACKING`. | Critical path = real Facebook ZIP→Memory[]; don't prioritize heatmap polish over parser. |
| [Time-Capsule-V2](repos/Time-Capsule-V2/STATUS.md) | 2026-08-06 | **Newly surfaced 2026-08-06** (had never been added to this table). V2 concept of TimeCapsule — went from bare scaffold to working build in one day: geo-map, analytics dashboard, working ZIP parser, cross-view deep linking, 9-fixture test matrix, 15-specialist audit pass (01–05). Has its own `CLAUDE.md`. | Ask the user whether this or the original **TimeCapsule** is the one to prioritize — audits flagged concrete bugs (duplicate renders, post-import routing, contrast). |
| [WatchMatch](repos/WatchMatch/STATUS.md) | 2026-07-31 | Has `CLAUDE.md` (authoritative). 20 commits, clean apart from 1 line. Local checkout was 5 commits behind `origin/main`, fast-forwarded 2026-08-03. | `README.md` has a stray uncommitted `- ^^` appended to the title — flagged, not fixed; ask the user before touching. |
| [MovieRecommendationBasedOnMood](repos/MovieRecommendationBasedOnMood/STATUS.md) ("MoodReel") | 2026-07-30 | Clean tree. Post-UI/UX-refinement pass. | Verify mobile audit findings (favorites.html breakpoints, navbar overflow) actually shipped in `2288a38`. |
| [Voxel-Modeling](repos/Voxel-Modeling/STATUS.md) | 2026-07-30 | Clean tree. Steady feature→fix cadence. | Audit other presets for undefined color constants (same bug class as the COPPER fix). |
| [TCRA-Code-Auditor-V4](repos/TCRA-Code-Auditor-V4/STATUS.md) | 2026-07-29 | Clean tree. Active — **this is the thesis-defense artifact** (user confirmed 2026-08-01). | Check other providers (Anthropic, etc.) for the same placeholder→real-model fix OpenAI/Gemini got. |
| [JU-PMIT-TCRA-Research](repos/JU-PMIT-TCRA-Research/STATUS.md) (private) | 2026-08-04 | Has its own `CLAUDE.md` (migrated 2026-08-03, authoritative). **Submission copy, pending compile check.** 144 commits, clean tree, pushed. 2026-08-04: length pass cut the numbered body 14.1% (2,914 words) toward an under-60-page target; no finding, number, citation or hedge changed, and all headings preserved in place because 59 cross-references are hard-coded literals. | **Compile decides whether the target was met — projection is 59.4–60.3 pages, straddling it.** Delete `reviews/` before submission (8 files still tracked/public). Git identity still unset — the 7 new commits carry the hostname address. Defense deck not re-checked against the condensed text. **New 2026-08-04: an ACADEMI.CX AI-detection scan flagged the submission text 54%, and a humanization pass is underway in a separate disconnected sandbox repo (`-humanize`), not yet ported back here** — ask the user for direction, see `STATUS.md`. |
| [PhysioTrace](repos/PhysioTrace/STATUS.md) | 2026-07-31 | Clean tree. Pulled 2 commits behind on add. | None currently. |
| [SpecMatch](repos/SpecMatch/STATUS.md) | 2026-07-31 | Clean tree. Pulled 2 commits behind on add. | Read `PLAN.md` in repo root for real direction. |
| [AstronomyDashboard](repos/AstronomyDashboard/STATUS.md) | 2026-07-31 | Clean tree, in sync. | None currently. |
| [entertainment-suite](repos/entertainment-suite/STATUS.md) | 2026-08-01 | **Resolved.** Gitlinks removed, `.claude/` gitignored (`059e088`). No local checkout (folder deleted) — the three worktrees' uncommitted work (new tests, `src/api/*`, `src/app.js`) was never committed and is presumed lost, not salvaged. API keys are server-side (Vercel proxies), not exposed. | None currently. |
| [Mouni](repos/Mouni/STATUS.md) (private) | 2026-08-02 | Stage 1 (Socratic), Layer 1 of 5 — blocked, awaiting user's answers, now including Q29-32/Q11a (its sandbox tool turned out pilot-ready, reopening the review-vs-empirical framing). 18 commits confirmed 2026-08-07, not a discrepancy. | None currently — waiting on user, not a blocker to flag. |
| [L2-Writing-AI-Sandbox](repos/L2-Writing-AI-Sandbox/STATUS.md) | 2026-08-01 | v1.2.0-stable, "Feature Complete," checkpoint says pilot-ready. No `CLAUDE.md` yet. | Reconfirmed 2026-08-07: 11 commits on `main` is the real count, settled — the "50" figure was a one-time recording error. |
| [DictatorBeingCancelledOverSocialMediaHype](repos/DictatorBeingCancelledOverSocialMediaHype/STATUS.md) | 2026-08-07 | "Digitally Cancelled?" theoretical paper on Bangladesh's 2024 uprising/blackout. 21 commits (up from 5), clean tree. PR merged 2026-08-06 adding LICENSE/CITATION.cff/NEXT_STEPS.md; feedback-implementation pass done (terminology, citations, CASED-model tension resolved). | Phase 3 pilot-corpus attempt hit a documented fetch-tool blocker, unresolved. Ask whether this is a second thread alongside JU-PMIT-TCRA-Research. |
| [listener-taste-growth-profile](repos/listener-taste-growth-profile/STATUS.md) | 2026-08-07 | Formerly tracked as `music-taste-age-research` (idea only, blocked on repo creation). The user created the repo themselves under this name. **v3.0, complete as a literature-review synthesis piece**, 13 commits, clean tree. | Empirical extension (listening-history-by-age-cohort) is future work, not started. Ask whether related to `bangladesh-music-evolution`. |
| [bangladesh-music-evolution](repos/bangladesh-music-evolution/STATUS.md) | 2026-08-07 | Academic research repo on Bangladesh's music culture, late 1970s–present. 53 commits, clean tree. **Grew a `web/` Next.js app same-day** (artists/concerts/genres pages + an interactive network graph, `vercel.json` present) — no longer Markdown-only. | Confirm the `web/` app scope was intended. Ask whether related to `listener-taste-growth-profile`. No `CLAUDE.md` despite now having real app code. |
| [med-tech-ocr](repos/med-tech-ocr/STATUS.md) | 2026-08-07 | Online doctor-consultation platform with OCR for prescriptions — originally an NSU CSE499 senior design project. Docs-only (3 commits; original report DOCX/PDF added same day), no app code checked in. GitHub repo is named `Med-Tech`, folder is `med-tech-ocr` — unreconciled. | Ask whether this is an active rebuild or an archival copy of a finished student project. |
| [brain-tumor-classification-efficientnet-gradcam](repos/brain-tumor-classification-efficientnet-gradcam/STATUS.md) | 2026-08-07 | PyTorch scaffold (dense EfficientNet + Grad-CAM) based on the user's NSU undergraduate thesis. `src/` pipeline written, thesis DOCX/PDF in `docs/` (PDF added same day). 10 commits, clean tree. No dataset yet, nothing trained/validated. | Untested end to end — needs the Kaggle dataset dropped into `data/raw/` and a real training run before trusting the scaffold. |
| [Blurt](repos/Blurt/STATUS.md) | 2026-08-11 | Voice-first intent-capture companion for ADHD users. Full frontend build QA'd against a refined mockup pass; new Task detail screen implements decomposition decision #8. Persona now wired into AI decisions. | Real-use test persona/inference + decomposition judgment quality. Reminder/Tone and Orchestrator agents unstarted. 4 self-test questions pending in ROADMAP.md. |

## Archived

Projects the user has confirmed are dead or fully superseded — moved out of the active table so
it stays a reliable "what's live" view instead of accumulating unresolved question marks.

| Project | Archived | Reason |
|---|---|---|
| [TCRA-Code-Auditor-V3](repos/TCRA-Code-Auditor-V3/STATUS.md) | 2026-08-01 | Complete, superseded by V4. User: "v3 is completed we are going to use v4 for thesis defense." The reverted `@import`/lockfile fix will not be re-landed. |
| [SwipeTrack](repos/SwipeTrack/STATUS.md) | 2026-08-01 | Hobby project, never shipped, "most likely dead" per the user, who asked for it to be dropped from daily activity. Don't prompt about it — they'll raise it if they return to it. |
| [tcra-thesis](repos/tcra-thesis/STATUS.md) (private) | 2026-08-01 | Superseded by `JU-PMIT-TCRA-Research`, 2026-08-01. Contents verified byte-identical (26/26 blob SHAs) before the switch. Repo still exists on GitHub; no local checkout. |
| `JU-PMIT-Thesis` → **renamed `citation-automation-`** (private, never tracked locally) | 2026-08-01 | Older, different artifact — Markdown (`Thesis.md`) + one-off Python citation scripts, no LaTeX. Not an earlier version of the LaTeX thesis. Re-verified 2026-08-01: the name `JU-PMIT-Thesis` now only resolves via GitHub's rename redirect; the repo is live-but-idle (private, **not** GitHub-archived, last push 2026-06-26) and holds no work the LaTeX thesis needs. |

## Code maps

**Migrating to project-local `CLAUDE.md` files (decided 2026-08-01)** — see
[`setup/project-template.md`](setup/project-template.md) for why and the target shape.
`file-map.md` (built 2026-07-31) was a copy of architecture facts mirrored from each project's real
repo, and copies drift: two of them were caught stale in the 2026-08-01 review (not "kept current
automatically" as this section previously, and wrongly, claimed). **WatchMatch**, **JU-PMIT-TCRA-Research** (migrated 2026-08-03), **TimeCapsule** (created with `CLAUDE.md` 2026-08-05), and **Time-Capsule-V2** (created with `CLAUDE.md` from its first commit) have their own `CLAUDE.md` so far; the other active projects still rely on `repos/<project>/file-map.md` until each one gets migrated on next real touch — except **DictatorBeingCancelledOverSocialMediaHype**, a pure-Markdown research repo with no code architecture, which skips this migration entirely (see its `references.md`). Check which applies in `references.md` before trusting either.

## Cross-project notes

- **TCRA-Code-Auditor-V4** and **JU-PMIT-TCRA-Research** are linked: V4's scoring prompt/rubric
  wording is pulled directly from the thesis (`Chap3/Chapter3.tex:127-146`). A change on one side
  likely needs a check on the other. Cite the LaTeX label `tab:tcra-rubric`, not a literal table
  number — the 2026-08-03 chapter restructure already renumbered the thesis's own tables once
  (Ch.4 analysis split into a new Ch.5), so any table number recorded here should be treated as
  stale on sight.
- All per-project files here are a **baseline snapshot from `git log`** (built 2026-07-31), not
  from session-by-session notes. Treat "Next steps" fields in each `STATUS.md` as best-guesses to
  confirm with the user, not settled fact, until they're updated by real sessions.

## Setup / tooling

Not a tracked project — see [`setup/`](setup/SETUP.md) for the statusline,
[`setup/agent-workflow.md`](setup/agent-workflow.md) for the commit-after-task workflow and default
3-agent model,
[`setup/agent-supervision.md`](setup/agent-supervision.md) for the 3 scheduled Routines (Sync/Health
Supervisor, Process-Improvement Agent, Per-Project Work Agent) that supervise all tracked projects
on a standing basis,
[`setup/machine-profile-mac-workspace.md`](setup/machine-profile-mac-workspace.md) for this
machine's Claude Code config snapshot (each machine gets its own `machine-profile-<name>.md`, never
a shared one), and [`setup/workflow-notes.md`](setup/workflow-notes.md) for how this user works — read that in full
when resuming, before anything project-specific, along with the "Standing directives" digest at the
top of [`setup/decisions-log.md`](setup/decisions-log.md).

Read on demand only, never as part of a routine resume: the rest of `decisions-log.md` (the
chronological log — provenance for *why* a rule exists), [`setup/skills-catalog.md`](setup/skills-catalog.md)
(picking a skill, briefing a subagent), and [`MAINTAINING.md`](MAINTAINING.md) (how to update this
repo — read before changing anything here).

**Per-machine setup — home PC done 2026-08-07, see `setup/machine-profile-homepc.md` for detail:**
1. **MCP server**: installed (`pip install --user mcp`) and registered (`claude mcp add --scope
   user claude-hub`) on home PC too. `claude mcp get claude-hub` verification was blocked by the
   session's Bash classifier — confirm `Status: ✔ Connected` next session there.
2. **Statusline sync-status segment**: home PC's workspace-root auto-git-sync hook was confirmed
   still live (a `Stop` hook, `sync-status.json` fresh), so the canonical `setup/statusline.py` was
   deployed to `~/.claude/statusline.py` there, with `CLAUDE_GIT_SYNC_WORKSPACE_ROOT` set via `setx`
   to the home PC's workspace path so the segment resolves correctly.
3. **New minor drift, home PC**: the workspace's top-level folder set no longer matches the
   2026-07-31 snapshot (`Blurt`, `JU-PMIT TCRA Research`, `L2-Writing-AI-Sandbox`, `WatchMatch` now
   present; `Skills`, `entertainment-suite`, both `Thesis Components*` gone) — not reconciled
   against this hub's tracked-project table yet, see the machine profile.
