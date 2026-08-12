# Workspace dashboard

<sub>**Claude: write-only file.** Never read this on resume — every fact here is already in
`INDEX.md` or a project's `LOG.md`. Update by prepending a new session entry and refreshing the
stat blocks. Rules in `MAINTAINING.md`.</sub>

`14 projects` · `391 commits` · `9 open items` · `1 uncommitted change` · updated **2026-08-08**

<sub>Only the **local** checkouts were re-measured 2026-08-04 with `git rev-list` (JU-PMIT-TCRA-Research
144, WatchMatch 20, Voxel-Modeling 7, TCRA-V3 7, TCRA-V4 5, Dictator… 5, SwipeTrack 3). Just one
moved: the thesis, 105 → 144, from the length pass below. The API-measured projects (PhysioTrace,
SpecMatch, AstronomyDashboard, entertainment-suite, Mouni, L2-Writing-AI-Sandbox — no local checkout
on this machine) were **not** re-queried this pass and are carried forward from 2026-08-03, so
treat those figures as of that date, not today. The uncommitted figure covers only local checkouts;
the API-measured projects have no working tree here, so their dirty state is unknown, not zero. The
1 uncommitted change is still WatchMatch's stray `- ^^` in `README.md`'s title (flagged below).</sub>

---

## Where the work is

Commit volume per project — where effort has actually gone.

```
JU-PMIT-TCRA-Res.    ██████████  144  ·  today
entertainment-suite  ████▋       68   ·  3d ago
TimeCapsule          ██▌         35   ·  1d ago
MoodReel             █▋          25   ·  5d ago
AstronomyDashboard   █▌          21   ·  5d ago
WatchMatch           █▍          20   ·  4d ago
Mouni                █▎          18   ·  2d ago
SpecMatch            █▏          17   ·  5d ago
L2-Writing-Sandbox   ▊           11   ·  3d ago
PhysioTrace          ▋           10   ·  5d ago
Voxel-Modeling       ▍            7   ·  5d ago
Dictator-...Hype     ▎            5   ·  1d ago
TCRA-V4              ▎            5   ·  6d ago
Blurt                ▎            5   ·  today
```

<sub>Bars rescaled — the thesis's jump to 144 compresses everything else. Two prior fixes rolled in:
L2-Writing-Sandbox and PhysioTrace were out of descending order, and the "today" markers were a day
stale for the projects last touched 2026-08-03.</sub>

**Two commit-count discrepancies resolved 2026-08-07** (fresh `--depth 50` clones, hashes match
current `main` HEAD on both):
- **Mouni**: 18 is the real count. The 10 previously recorded was simply stale, not a discrepancy.
- **L2-Writing-AI-Sandbox**: 11 is the real count, reconfirmed. The 50 recorded 2026-08-02 was a
  one-time recording error — no rewritten or lost history.

**A previously-untracked project surfaced: DictatorBeingCancelledOverSocialMediaHype**, an academic
paper (not code) on Bangladesh's 2024 uprising and the failed internet blackout. See the session
entry below.

**The thesis repo's commit count is an artefact of the now-removed auto-sync hook**, which used to
commit once per file edit — a single revision pass became dozens of commits. The hook itself was
removed 2026-08-05 (see the session entry below); the historical per-edit commits remain in the
thesis repo's history, they just won't keep accumulating that way going forward.

## What to do next

Seven open items. No Decide-tier blockers currently — both entertainment-suite items closed
2026-08-01, and the thesis's own review items are all applied or author-deferred as of 2026-08-03.

| # | What | Why now | Effort |
|---|---|---|---|
| 1 | **Compile the thesis** — and this now decides whether the page target was met | Still never compiled; no LaTeX toolchain on this machine. After the 2026-08-04 length pass the projected body is **59.4–60.3 pages against an under-60 target**, so it genuinely straddles the line and only the compile resolves it. Delete `output.aux`/`output.bbl` first, then `pdflatex → bibtex → pdflatex ×2`, and read off where Chapter 6 ends. If it's over, the next ~500 words come from §6.1, §5.6, §5.7. | 5 min, yours |
| 1b | **Delete `reviews/`** from the thesis repo before submission | Re-verified 2026-08-04: 8 files still tracked and public, holding the full 40-item critique of the thesis. Long-standing, and the one item with real exposure. | XS, yours |
| 1c | **Set the git identity** in the thesis repo | Re-verified 2026-08-04: `user.name`/`user.email` both unset. The 7 length-pass commits are authored `Ismail Hossain <ismailhossain@Ismails-iMac.Dlink>` and won't link to your GitHub account. Fix before further commits — pushed history was deliberately left alone this close to the defense. | XS, yours |
| 8 | **Re-check the defense deck against the condensed thesis text** | The 2026-08-04 length pass changed no number and no finding, so the deck *should* still be accurate — but that was reasoned, not verified. The deck has drifted from the text once before (6 of 20 results rows stale, caught 2026-08-03), which is why "should be fine" isn't good enough here. | S |
| 2 | Verify **MoodReel**'s mobile fixes actually shipped | An audit found `favorites.html` had zero breakpoints and the navbar could overflow. A later commit *claims* fixes but doesn't itemise them. Unconfirmed either way. | M |
| 3 | Audit **Voxel-Modeling** presets for undefined colours | The COPPER bug renders voxels white and fails *silently*. Same class of bug could be sitting in any other preset. | M |
| 4 | Check **TCRA-V4**'s remaining providers for model-ID drift | OpenAI and Gemini both needed fixes; Anthropic and Groq haven't been checked against live docs. Note the rubric it scores against lives in the thesis repo's Chapter 3 (cite label `tab:tcra-rubric`, not a table number — it renumbered once already). Also worth checking V4 for the CSS `@import` order bug that V3 hit. | S |
| 5 | Read **SpecMatch**'s `PLAN.md` before trusting its `STATUS.md` next-steps | `STATUS.md` here was seeded from `git log` alone (2026-07-31 baseline), so its "next steps" are a best-guess — `PLAN.md` in the repo root has the real direction and hasn't been folded in yet. | XS |
| 6 | Confirm what to do with **WatchMatch**'s stray `README.md` edit | One uncommitted line — `# 🎬 WatchMatch - ^^` — sitting in the working tree. Looks accidental, not fixed without asking since intent is unclear. | XS |
| 7 | Get direction on **DictatorBeingCancelledOverSocialMediaHype** | Newly tracked this pass, discovered on disk rather than described by you — an academic paper on the 2024 Bangladesh uprising, no code. Unknown whether the proposed empirical follow-up is planned, or how (if at all) it relates to the JU-PMIT thesis work. | XS |

<sub>Not a numbered item, but worth flagging: two commit-count figures didn't reconcile this pass —
**Mouni** (18 now vs. 10 recorded) and **L2-Writing-AI-Sandbox** (11 now vs. 50 recorded) — see
"Where the work is" above. Neither is escalated to a blocker; both are just recorded as observed
rather than resolved. Also: **Mouni** gained two new Socratic questions (Q29-32) after its own
empirical-study tool ([L2-Writing-AI-Sandbox](repos/L2-Writing-AI-Sandbox/STATUS.md)) turned out
pilot-ready rather than unbuilt — still just "waiting on the author," not escalated either.</sub>

## Worth trying

Skills available but never used here, picked because they fit something above — not generic suggestions.

- **`/run`** → item #2. Launches the app so mobile fixes get *verified* rather than assumed. This is
  the exact gap that left MoodReel's audit findings unresolved.
- **`/security-review`** → MoodReel hardcodes a demo OMDB key across 4 files and has never had a
  real security pass. (entertainment-suite was on this list until 2026-08-01 — checked and cleared:
  both its keys are server-side behind Vercel proxies, `src/api/fetch-news.js:4` and
  `src/api/omdb-proxy.js:5`.)
- **`/init`** → 9 of 13 projects have no `CLAUDE.md` (one more, Dictator..., is pure Markdown
  research with no architecture to document — not a candidate). WatchMatch and the thesis repo have
  one each, and they're the only two where Claude can skip re-reading the codebase from scratch.

---




### 2026-08-12 — First Hermes Agent integration on Ismail-hp (Windows, API-only)

Started a new machine in the claude-hub footprint: **Ismail-hp**, a Windows 10 device with no local workspace checkout. Authenticated `gh` CLI as **smile-plzz** (via device-flow browser authorization) and ran `gh auth setup-git` so git uses `gh` for HTTPS credentials. This is the third tracked machine after the Mac workspace and the home PC — different runtime (Hermes Agent CLI, not Claude Code CLI) and different posture (GitHub API access only, no local project trees checked out).

**What happened this session:** read `claude-hub` in full to learn the workflow (README, CLAUDE.md, INDEX.md, MAINTAINING.md, workflow-notes.md, decisions-log.md standing directives, agent-workflow.md, project-template.md, machine-profile-homepc.md, and the Blurt project's STATUS/LOG/references) before touching anything. Auth setup is the only concrete outcome so far — no tracked project cloned, no code touched.

**State recorded:**
- Created `setup/machine-profile-ismailhp.md` — fresh profile for this device (identity, auth state, tooling, workspace-none, relationship to other tracked machines).
- Git identity still **unset** on this machine — flag if commits land before it's fixed (same standing gap as home PC / Mac at their first touch).

**Open question, not decided:** whether this machine gets a local workspace checkout (clone the OneDrive workspace, or a fresh path) or stays API-only (read/update claude-hub, triage, open PRs against tracked repos without a local tree). Left un-decided rather than assumed — ask before picking a path.

**CLAUDE.md checked — no cross-references or rules triggered by this session.** This entry exists so a future session on Ismail-hp can resume without re-deriving the integration state; the workflow itself didn't change (no new standing directive, no project state change).

### 2026-08-08 — New project: Blurt, an ADHD intent-capture app — schema + first working prototype

Started and built out a brand-new project, `smile-plzz/Blurt` ("just blurt it out"), a voice-first
companion for ADHD users that captures a fleeting intention the instant it forms instead of letting
it evaporate before it reaches a todo list — explicitly not a todo app. The user supplied an 8-agent
build plan (`AGENTS.md`) and the product rationale doc (`blurt-concept.md`); the repo was scaffolded
to match: versioned JSON schemas for an intent's full lifecycle and the per-user persona (`schema/`),
plus stub folders for the six other agents not yet built.

The **Capture Agent** is the first piece actually working, not just planned: a no-build-step PWA
(`capture/web/`) with voice capture via the browser's `SpeechRecognition` API and an always-visible
typed fallback, writing straight to `localStorage`. Tested live in Chrome rather than just reviewed —
both paths correctly saved schema-valid intents, with real mic audio actually transcribed. That test
also surfaced two real findings worth flagging: the mic can fire from stray keyboard focus with no
visible recording indicator (a UX hardening gap), and Chrome's `SpeechRecognition` sends raw audio
off-device for transcription, which is a live exception to the repo's local-first privacy stance, not
a hypothetical — recorded as an open decision in `PRIVACY.md` rather than left implicit.

Added the project's own `CLAUDE.md` on first real code work (per the standard template), so this is
the 5th tracked project with one instead of a `file-map.md`. Next up per the build order: Reminder/
Tone Agent (parallelizable against fake data).

### 2026-08-07 — Re-audited the 5 recently-discovered repos; two had real progress, one grew a whole app

Checked the five projects surfaced from disk the same day (DictatorBeingCancelledO

Started a new machine in the claude-hub footprint: **Ismail-hp**, a Windows 10 device with no local workspace checkout. Authenticated `gh` CLI as **smile-plzz** (via device-flow browser authorization) and ran `gh auth setup-git` so git uses `gh` for HTTPS credentials. This is the third tracked machine after the Mac workspace and the home PC — different runtime (Hermes Agent CLI, not Claude Code CLI) and different posture (GitHub API access only, no local project trees checked out).

**What happened this session:** read `claude-hub` in full to learn the workflow (README, CLAUDE.md, INDEX.md, MAINTAINING.md, workflow-notes.md, decisions-log.md standing directives, agent-workflow.md, project-template.md, machine-profile-homepc.md, and the Blurt project's STATUS/LOG/references) before touching anything. Auth setup is the only concrete outcome so far — no tracked project cloned, no code touched.

**State recorded:**
- Created `setup/machine-profile-ismailhp.md` — fresh profile for this device (identity, auth state, tooling, workspace-none, relationship to other tracked machines).
- Git identity still **unset** on this machine — flag if commits land before it's fixed (same standing gap as home PC / Mac at their first touch).

**Open question, not decided:** whether this machine gets a local workspace checkout (clone the OneDrive workspace, or a fresh path) or stays API-only (read/update claude-hub, triage, open PRs against tracked repos without a local tree). Left un-decided rather than assumed — ask before picking a path.

**CLAUDE.md checked — no cross-references or rules triggered by this session.** This entry exists so a future session on Ismail-hp can resume without re-deriving the integration state; the workflow itself didn't change (no new standing directive, no project state change).

verSocialMediaHype,
bangladesh-music-evolution, brain-tumor-classification-efficientnet-gradcam, med-tech-ocr,
listener-taste-growth-profile) against their actual `git log` since being added, and updated
`STATUS.md`/`INDEX.md` for the ones that moved:

- **DictatorBeingCancelledOverSocialMediaHype**: 5 → 21 commits. A `research-completion` PR merged,
  adding LICENSE/CITATION.cff/NEXT_STEPS.md, plus a feedback-implementation pass (terminology,
  citations, CASED-model tension resolved). A Phase 3 pilot-corpus attempt hit a documented
  fetch-tool blocker, still open.
- **bangladesh-music-evolution**: 48 → 53 commits, and — the real finding — it's no longer a
  Markdown-only research repo. A `web/` Next.js app was scaffolded and built out same-day: artist/
  concert/genre pages plus an interactive network-graph visualization, with a `vercel.json` present.
  Worth confirming with the user whether that scope was intended.
- **brain-tumor-classification-efficientnet-gradcam** and **med-tech-ocr**: minor doc additions only
  (PDF thesis copy; original research report DOCX/PDF) — commit counts otherwise unchanged.
- **listener-taste-growth-profile**: no change since last check, still 13 commits.

### 2026-08-06 — Synced all GitHub repos; added TimeCapsule and Time-Capsule-V2 to tracking

Pulled latest changes from origin/main. TimeCapsule (smile-plzz/TimeCapsule) was created
2026-08-05 with 35 commits — UI prototype on main (React/Vite/TS + sample data), any-day
explorer, heatmap, search, collections, compare years demoable. ZIP parser still stubbed
(`jszip` present, unused). Added to tracking with STATUS.md, LOG.md, and references.md.

Also discovered **Time-Capsule-V2** (smile-plzz/Time-Capsule-V2) — a separate repo pushed
2026-08-06 with a single commit on main. Added to tracking as a new project.

### 2026-08-05 — Auto-git-sync removed everywhere; replaced with commit-after-task and a default 3-agent workflow

You said the auto-sync hook was "causing a mess" and asked for it gone entirely, replaced with
Claude committing and pushing itself once each task is done — plus a new standing default of 3
always-ready agents that can spawn as many specialized subagents as a task needs, working
simultaneously as long as their work doesn't overlap.

**Removed:** `setup/hooks/auto-git-sync.py`, `setup/auto-git-sync-homepc.py`, and
`setup/statusline-mac.py` (an archived reference copy that only existed for the git-sync segment).
The statusline no longer shows a git-sync status segment — `sync-status.json` isn't written by
anything anymore, so it would only ever show stale data.

**Replaced with a workflow, not a script** — see the new `setup/agent-workflow.md`: Claude commits
once a task is actually finished (not per file edit) and pushes right away, and the default is 3
top-level agents that can each spawn autonomous, task-specialized subagents, gated on partitioning
work so nothing overlaps. `CLAUDE.md`, `setup/SETUP.md`, `INDEX.md`, `setup/workflow-notes.md`, and
both machine-profile files were updated to stop describing the old hook as current state.

**If either machine still has the old hook wired into its `settings.json`**, remove the
`PostToolUse`/`Stop` entries pointing at `auto-git-sync.py` — the script itself is gone from this
repo, so those entries would just fail silently.

### 2026-08-04 — Thesis body cut 14% for the page limit, and the obvious tool for the job turned out to be unusable

You needed the numbered body of the thesis under 60 compiled pages, down from about 68, and you
wanted the condensed prose not to read as AI-written. Both done, with one honest gap at the end.

**Cut 2,914 words (14.1%) across Chapters 1–6** — Ch5 took the most (−1,075), Ch2 next (−707). The
cuts went after restatement, not evidence: the auditor's architecture in §5.4 was re-describing what
Ch4 and Appendix B already say, §6.1 was restating your introduction and abstract, and §3.1.1
defined the four TCRA properties a second time when Table 3.1 and the rubric already had them. No
score, mean, α value, threshold, citation or hedge changed anywhere.

**The thing worth knowing for next time:** your thesis has 59 cross-references written as literal
text (`Section 5.3.2`) rather than as LaTeX `\ref{}`. Delete or merge any numbered heading and every
one of those silently points at the wrong place, with no warning from LaTeX at compile time. So
every heading was kept exactly in position and the condensing happened inside them. A second trap
found the same way: 29 of your 46 references are cited exactly once, mostly in Chapter 2 — cutting
a sentence there could have quietly dropped a source from your bibliography. All 46 survived.

**The ARS academic-paper skill's revision mode looked perfect for this and could not be used.** It
advertises exactly the right protection — refuse the edit if a heading gets rewritten or the section
count changes. But its parser only understands Markdown: it would have injected `<!--block:B0001-->`
markers that render as **literal visible text in your PDF**, and it reads `\section{...}` as
ordinary prose, so the heading protection would never have triggered at all. It would have looked
safe while doing nothing. Wrote a LaTeX-specific replacement instead and deliberately tried to break
it first (dropped a subsection, removed a citation, altered an α value — it caught all of them).

**On the AI-detection concern:** loaded the humanizer rules *before* drafting rather than cleaning up
afterward, because a retrofit swaps vocabulary but leaves the machine-like sentence shapes. Across
the body: "not X but Y" 28 → 6, semicolons 58 → 31, and the formulaic paragraph openers ("Three
qualifications apply", "Five limitations bear on this study") 11 → 1. Average sentence length came
down from 26.2 to 24.3 words and the share of very long sentences from 25% to 19% — that unvarying
mid-length rhythm was the strongest tell in the draft.

**What's not finished:** the projection is 59.4–60.3 pages, which straddles your target. The
uncertainty is real — it depends on how much page space your 10 tables and 4 figures actually take,
and there's no LaTeX toolchain here to measure it. Your compile settles it, and if it comes in over
60 the next ~500 words should come from §6.1, §5.6 and §5.7. Past that point, cutting starts costing
substance rather than repetition. Also re-checked your three standing items rather than repeating
them from notes: `reviews/` still has 8 files tracked and public, your git identity is still unset
(so today's 7 commits carry the machine-derived address), and the defense deck has **not** been
re-verified against the shortened text — it should be fine since no number moved, but that's
reasoning, not checking, and the deck has drifted once before.

### 2026-08-03 — Routine sync: a stale local checkout, a big untracked thesis pass, and a new project found on disk

You asked to "sync and read the repo and then update accordingly." Three real findings, none of
them from you describing new work — all surfaced by actually checking git state against what was
recorded.

**WatchMatch's local checkout on this machine was silently 5 commits behind `origin/main`.**
`git status` reported "up to date" because its remote-tracking ref was stale — no fetch had run.
A `git fetch` showed two more `api/chat.js` recommendation-guideline revisions, an `index.html`
update, and a `CLAUDE.md` edit, none of which touched `README.md`. Fast-forwarded safely (no
conflict with the pre-existing uncommitted change there). Separately, that uncommitted change is no
longer the one recorded 2026-07-31 (it landed) — it's now a stray one-line `- ^^` appended to the
`<h1>`, flagged rather than fixed since the intent isn't obvious.

**JU-PMIT-TCRA-Research had a large untracked session.** Since the 2026-08-01 baseline, the thesis
went through a chapter restructure (analysis split out of Chapter 4 into a new Chapter 5, tables
renumbered — the old "Table 4.1" is now 4.2), a citation fix (`simon1969` didn't discuss program
synthesis in the cited sense — landed via PR #1), and a full realignment of the defense deck to the
corrected text (6 of 20 results-table rows had gone stale; headline corrected from "16 of 20" to
"15 of 20"). It also picked up its own `CLAUDE.md`, migrating off the mirrored `file-map.md` — now
retired for this repo, per the 2026-08-01 decision to make project-local `CLAUDE.md` the
architecture source of record.

**A previously-untracked project surfaced: DictatorBeingCancelledOverSocialMediaHype**, found by
listing the workspace root rather than through anything you'd described. It's an academic paper —
"Digitally Cancelled?" — on the 2024 Bangladesh uprising and the government's internet blackout, 5
commits, no code. Given a baseline `STATUS.md`/`LOG.md`/`references.md` and added to `INDEX.md`.
Direction is unknown; it's item #7 above.

**Two commit-count figures didn't reconcile against what was previously recorded** — Mouni (18 vs.
10) and L2-Writing-AI-Sandbox (11 vs. 50) — and neither was chased down this session. Recorded as
observed, flagged rather than silently overwritten as fact, per the "verify before you write" rule
this repo carries after an earlier confidently-wrong note.

### 2026-08-02 — Hub caught up on real work that happened outside it: new project found, thesis and entertainment-suite dashboard both stale

You asked to "read and update" with no target, then flagged that repos had moved since the last
update. They had, in three places this dashboard hadn't caught up to:

**A previously-untracked project surfaced: L2-Writing-AI-Sandbox.** Not new work — it already had 50
commits and a 2026-06-18 checkpoint tagging it v1.2.0-stable, "Feature Complete," "ready for pilot
clinical trials." It came to light through **Mouni**, whose PhD-proposal-to-lit-review reframing had
assumed the proposal's study tool was unbuilt. It isn't: this *is* that tool, and it already
instruments the proposal's exact constructs (anxiety/self-efficacy check-ins, multi-LLM gateway,
researcher dashboard). Added to `INDEX.md`, given a baseline `STATUS.md`/`file-map.md`. Mouni's
`PLAN.md` and `SOCRATIC_QUESTIONS.md` picked up two new questions (Q29-32, Q11a) reopening — not
resolving — whether this changes the review-vs-empirical call. Pipeline is still blocked awaiting
your answers, same as before, just with more to answer.

**The thesis (JU-PMIT-TCRA-Research) had two real sessions this dashboard never recorded.** An
AI-detection pattern audit (source-side, not a detector run) rewrote six prose spans across three
chapters — tricolon density and "Taken together"/"not X but Y" constructions concentrated in the
conceptual chapters — with zero citation keys or digits touched. Separately, a fourth conclusion was
added to Chapter 4: no evaluator ever assigned a 0 on any dimension across all 400 scores, so the
nominal 4-band scale (0–3) was observed as effectively 3 bands — the bottom band was unreachable by
construction, not just unobserved. Neither change touches the known-correct values already recorded
in `STATUS.md` (T/C/R/A means, α values). Still not compiled — item #1 below.

**entertainment-suite's two Decide items had already been resolved on 2026-08-01, but only its own
`STATUS.md` knew it — `INDEX.md` and `LOG.md` were still showing them open.** The gitlink push landed
clean (`059e088`), and the salvage-vs-discard question resolved itself by default: the three
worktrees' uncommitted work was never committed and existed only in the local folder, which was
already deleted by the time this was checked. Presumed lost, not salvaged. Both items are now closed
everywhere in the hub, not just in the one file that had it right.

**Lesson for next time:** a `STATUS.md` getting updated correctly doesn't mean `INDEX.md` and
`LOG.md` did too — check all three when closing something, not just the one you happened to be
editing.

### 2026-08-01 — All four open questions answered; one instruction deliberately not carried out

You cleared the whole Decide list. Three answers landed as given: **TCRA-V3 is complete** and V4 is
what you'll defend with, **SwipeTrack** is a dead hobby project to stop tracking, and **`JU-PMIT-Thesis`**
was already handled. Both finished projects moved to Archived. Checking the third turned up a detail
worth knowing: that repo no longer exists under that name — it was **renamed `citation-automation-`**,
and the old name only still resolves through GitHub's rename redirect. It's private, idle since
26 June, and holds nothing the LaTeX thesis needs. It is *not* GitHub-archived, contrary to how it
had been described here.

**The fourth answer — "push" for entertainment-suite's `.claude/` — took three attempts and the
result is a defect.** The folder isn't project config: it's three abandoned Claude Code agent
worktrees, ~18,000 files including a full `node_modules`, plus a `.env` per worktree holding
`OMDB_API_KEY` and `GNEWS_API_KEY`. Since the repo is public, the first pass gitignored it rather
than pushing. You asked again, removed the root `.env`, and `.env` was gitignored so the worktree
copies stayed local.

**What landed isn't files.** Each worktree has a `.git` file, so git recorded three *gitlinks*
(mode `160000`, all pointing at `a561a05` — master itself) instead of content. No `node_modules`,
no `.env`, none of the worktree edits. GitHub renders them as grey folders that resolve to nothing;
a fresh clone gets three empty directories. That's item #2: drop the gitlinks and ignore `.claude/`,
or land the worktree work as real commits.

Which matters because **the worktrees contain real uncommitted work** — three new test files, edits
across `src/api/*` and `src/utils/api.js`, and a modified `src/app.js` — invisible to a normal
`git status`, and a routine `git worktree prune` deletes them without warning. Nothing was pruned.

One correction: an earlier draft of this page said those API keys were exposed client-side. **They
aren't.** Both are read server-side inside Vercel functions (`src/api/fetch-news.js:4`,
`src/api/omdb-proxy.js:5`) and never reach the browser. entertainment-suite is off the
security-review list.

Separately, a claim in this repo's own `CLAUDE.md` was found to be **wrong and has been corrected**:
it said the auto-git-sync hook applies only to claude-hub, not to project repos. It doesn't — the
hook is installed workspace-wide at `Desktop/Claude/.claude/`, and the `.gitignore` edit above
auto-committed to entertainment-suite with no `git add`. Practical effect: any edit to any project
repo in this workspace commits and pushes by end of turn, so there's no "leave it dirty for review"
option. Decide before editing.

### 2026-08-01 — Architecture truth moves into each project's own `CLAUDE.md`; `file-map.md` retired going forward

Follow-up to the same-day self-audit below: you asked what a project-local doc structure would
actually improve over the mirrored `file-map.md` model. The two stale file-maps found in that audit
are the answer — both were the same failure shape, a copy drifting from a second, easy-to-forget
edit in a different repo than the code change.

**New rule, written into `MAINTAINING.md` and `CLAUDE.md`:** a project's own `CLAUDE.md` (shape
defined in the new `setup/project-template.md`) is now the authoritative architecture source,
created the first time real code work happens on a project without one — same trigger `file-map.md`
used to have. It replaces `file-map.md` for that project once it exists; `STATUS.md` here shrinks to
a digest + pointer instead of re-explaining the codebase. `WatchMatch/CLAUDE.md` is the working
example this was modeled on.

**Not done, and worth being clear about:** this is a decision and a template, not a rollout. Only
WatchMatch has its own `CLAUDE.md` today. The other eleven projects still lean on `file-map.md`
(now marked legacy in `MAINTAINING.md`) until each gets migrated on its next real touch — that's by
design (build it when there's real work to justify exploring the tree), not an oversight.

### 2026-08-01 — Hub self-audit from Cowork: dashboard drift caught, two stale file-maps fixed, Cowork gap documented

You asked for a review of claude-hub against its own stated intent, done from a Cowork session (not
Claude Code CLI) — worth noting because that's exactly what surfaced part of what follows.

**This dashboard had already drifted from `INDEX.md`, the failure mode the paired-update rule
exists to prevent.** SpecMatch has carried a live `INDEX.md` flag ("read `PLAN.md` for real
direction") that never made it into this table or the open-items count. Added as item #10; count
corrected 9 → 10. Worth a standing habit: when a new `INDEX.md` flag is added, check this table in
the same edit, not just the reverse.

**Two `file-map.md` files were stale, caught by literally doing what `CLAUDE.md` step 5 says to
do** — diffing the "verified against commit" hash against `git log -1`. WatchMatch's map was 4
commits behind (missed a system-prompt rewrite in `api/chat.js` and two new helper functions in
`index.html`'s OMDb resolution chain). The thesis map was 1 commit behind (missed the new
`reviews/ai-detection-audit-worklist.md`). Both refreshed with real content changes, not just a
hash bump. Two-for-two stale on the only file-maps checkable from this machine suggests the
staleness marker isn't getting refreshed reliably when commits land — worth watching, not yet worth
a process change.

**Real gap: the "auto-git-sync handles it" premise in `CLAUDE.md` is Claude-Code-hook-specific and
silently doesn't hold in a Cowork session.** The hook lives in Claude Code's `settings.json` and
fires on Claude Code's own tool-execution hooks — nothing in Cowork's execution model triggers it.
`CLAUDE.md` and `setup/skills-catalog.md` now say so explicitly. Practical effect right now: the
edits in this session were committed and pushed by hand (see below), not by the hook.

**Not real: this sandbox's `git status` shows nearly every tracked file as modified.** Diffed a
sample — pure CRLF/LF noise from how this particular mount handles line endings (identical
insertion/deletion counts, zero content change), not real uncommitted work. Recorded here so a
future session doesn't mistake it for the hook being broken.

### 2026-08-01 — Thesis build errors cleared; git auto-sync stops pushing on every keystroke

Six LaTeX/BibTeX errors from your build log are fixed. One of them was the real problem and the
other five were small:

**Your bibliography style was silently breaking every citation that prints an author name.**
`ieeetr` isn't compatible with the `natbib` package the thesis loads — it writes bare reference
entries with no author attached, so every `\citet{...}` in the text had nothing to print. That's
why Turing, Searle and Vygotsky were flagged and nobody else: those are the only citations written
in the author-naming form. Nothing was wrong with the `.bib` entries themselves. Switched to
`unsrtnat`, which looks identical (numbered, in citation order) but works with natbib.

The rest: a duplicate `chap:Intro` label (the leftover half of a commented-out chapter heading in
`thesis.tex`), a too-strict `[h]` table placement in Chapter 3, and three malformed `.bib` entries.
The error blaming Chapter 5 for duplicate labels was a red herring — that file has no labels at
all; it just happened to be the last one LaTeX read.

**You need to compile it.** There's no LaTeX installed on this machine, so none of this has been
verified by actually building the document — it's item #5 on the list above. Delete the old
`output.aux` and `output.bbl` first, or the stale bibliography file will keep reporting the same
errors after they're fixed.

**Separately: pushes are now batched.** You noticed six edits produced four separate pushes and
asked for them grouped, with a visible confirmation. The sync hook now commits locally on every
edit as before, but only pushes once when a turn finishes. The status bar shows `⇡3` while commits
are waiting and `✅ pushed successful` for five minutes after they go out — so "did that push?"
should be answerable at a glance instead of by asking. One trade-off worth knowing: if a session is
killed mid-turn, commits sit locally unpushed, and the `⇡N` marker is what tells you.

### 2026-08-01 — Thesis published as its own private repo; two old thesis repos retired

Your thesis folder (`JU-PMIT TCRA Research`) turned out not to be a git repo at all — just a loose
copy of files sitting in the workspace. It's now **`smile-plzz/JU-PMIT-TCRA-Research`**, private,
one commit, 26 files, pushed.

**Before creating it, the folder was checked against the existing private `tcra-thesis` repo, and
the two were identical** — all 26 file hashes matched exactly. So nothing was stranded outside git,
and `tcra-thesis` is now a duplicate under a name you're not using. It's archived: still on GitHub,
no local copy, no further work there.

**The two-thesis-repos question is answered.** `JU-PMIT-Thesis` is *not* an earlier version of the
same document — it's Markdown (`Thesis.md`) plus a handful of one-off Python citation scripts, with
zero files in common with the LaTeX source. It reads as an older drafting workflow, so it's archived
too. That's a judgement from the file contents, not your confirmation — item #3 on the list above
exists so you can overrule it.

**Three errors in the old code map were corrected while writing the new one.** There's no
`Appendices/` folder (the old map said there was an empty one), the two files in `Intro/` aren't
actually pulled into the document by `thesis.tex`, and `aas_macros.sty` is committed but its import
line is commented out. Table 3.2 — the rubric TCRA-Code-Auditor-V4 quotes — is at
`Chap3/Chapter3.tex:127-146`, not the 125-145 previously recorded. Worth knowing: that "3.2" is
LaTeX auto-numbering based on table order, so inserting any table earlier in Chapter 3 renumbers it
silently and breaks the cross-repo reference. Cite the label `tab:tcra-rubric` instead.

Also cleared two stale flags off this dashboard: WatchMatch's uncommitted `README.md` (tree is clean
— it landed) and "test the cross-machine path," which the 31 July session already proved. And every
commit count in the dashboard above was re-measured rather than carried over — the previous figures
were a Mac snapshot mixed with a partial home-PC count, and were wrong for WatchMatch by 5 commits.

**Not done:** the other ten projects' `STATUS.md` files were not refreshed this session — only the
thesis entry and the index/dashboard were. One thing worth flagging: an auto-git-sync hook is active
repo-wide, not just in claude-hub. It committed the whole thesis tree by itself the instant the
first file was written, before a commit message could be chosen (that commit was amended). Expect it
to auto-commit in any repo you work in.

### 2026-07-31 — First resume from the home PC

Cloned claude-hub onto the home PC for the first time and ran the resume checklist end to end —
item #9 from this dashboard, "test the cross-machine path," is now actually proven rather than
aspirational.

Found the home PC already had its own `statusline.py` and `auto-git-sync.py`, built independently
before this repo existed — exactly the scenario the Mac session had flagged and deliberately left
unresolved. Captured both as separate files (`statusline-homepc.py`, `auto-git-sync-homepc.py`) for
comparison rather than letting either silently overwrite the other; reconciling them into one
canonical version is still an open call.

**New finding:** this machine's 8 project folders (AstronomyDashboard, Mouni, PhysioTrace, Skills,
SpecMatch, Thesis Components, Thesis Components Humanized, entertainment-suite) share zero overlap
with the 7 projects tracked from the Mac. None added to the tracked table — whether to bring any in
is a decision for the user, not assumed here. Also confirmed caveman works fine on this machine
(Node is installed), unlike the Mac where it's disabled for missing Node — a real per-machine
difference, not a bug anywhere.

### 2026-07-31 — claude-hub built from scratch

Set this repo up so work can move between the Mac, home PC, and office PC without re-explaining
context each time. Also ran a cleanup pass on the Claude Code install itself.

**Cleanup:** disabled three unused things — the `use-railway` skill and `railway` connection (zero
usage on record) and the `caveman` plugin, which was broken here anyway: its hooks need Node.js,
which isn't installed, so it had never actually run. All reversible; nothing deleted.

**The hub:** all 7 projects got a status page, change log, and code map. The code maps were built by
actually reading each codebase, which is where items #5–#8 above came from — none of them were
visible from commit history alone.

**Tooling backed up:** the auto-git-sync hook and statusline existed only on this Mac, in no repo —
if the drive died they were gone. Both are here now with porting instructions. That also surfaced a
setup note never written down safely: the git hook must live in `settings.json`, never
`settings.local.json`, or Claude Code silently wipes it next time a permission is approved.

**Efficiency:** trimmed what Claude loads per resume by 47% (~8.4k → ~4.4k tokens) by splitting
read-path from write-path docs and cutting content that duplicated what every session already
receives automatically.

**One correction worth noting:** a "lesson learned" written earlier that day turned out to be
factually wrong, and was only caught by re-checking raw timestamps. The repo now carries an explicit
rule to verify claims before recording them — a confident wrong note is worse than no note.