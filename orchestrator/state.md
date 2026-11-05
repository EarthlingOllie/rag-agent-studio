# Ticket frontier: claim, build, test, evidence, PR->candidate, merge, mark done; repeat
MODE:      autonomous · waves 15/25 used · SCRATCH=/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad
GOAL:      every unblocked ticket (and those unblocked in turn) built, evidenced in docs/tickets/<spec>/<ticket>-evidence/, PR'd into candidate, merged, marked done
STATUS:    PAUSED by orchestrator at user usage limit (97% of 5h). All wave-15 workflows stopped. Resume: relaunch ship.js (localMerge:true) for 04-01, 03-06, 03-09, 03-05 first (max 4 at once), then 03-03, 02-06, 03-04, 03-08 (real HF models). Each resumes its pushed ticket branch + scratch worktree. Then gap-closure pass for 03-02 crit 6
KNOWN:     orientation (specs, 78 tickets, deps, planned toolchain): SCRATCH/orientation.md; frontier helper SCRATCH/bin/frontier.py
KNOWN:     dispatch script copy SCRATCH/plugin/dispatch.js; compact ship-one-ticket SCRATCH/plugin/ship.js — launch as Workflow({scriptPath: ship.js, args:{now,scratch,t:{id,spec,ticket,name,slug,dependsOn,notes?,infra?}}}) directly (workflow nesting is 1 level; never wrap it)
KNOWN:     scratch survives container restarts; restart kills running workflows -> re-dispatch (workers resume from remote branch/PR)
KNOWN:     DONE (PR#): 01-01..01-12 (#1,#2,#3,#6,#11,#13,#9,#14,#16,#15,#10,#17) · 02-01 #20 · 02-02 #22 · 02-03 #21 · 02-04 #23 · 02-05 #19 · 03-01 #18 · 03-02 #24 · 09-01..09-05 (#5,#4,#7,#8,#12) — 24 tickets, candidate @0a6a9e7
KNOWN:     ticket id/branch/evidence path must be explicit in context AND stage tasks (ship.js does this)
RULED OUT:
BLOCKER:   Actions down repo-wide; USER AUTHORISED merging on local test results (09:2xZ). ship.js now takes args.localMerge=true -> merges (merge commit) on local green without CI. Retry trigger deleted.
DECISIONS: mode autonomous — user authorised create+merge PRs into candidate; user set wave budget 25
DECISIONS: convention — claim = commit "**Status:** in-progress" on ticket branch pushed first; done = "**Status:** done" in the ticket file within the ticket's PR
DECISIONS: branch per ticket ticket/<ticket-id>-<slug> from origin/candidate
DECISIONS: rolling waves — launch newly unblocked tickets as each result lands
DECISIONS: limits stated to user — merge only into candidate, never main; no terraform apply / real cloud resources / real OIDC / real provider keys; human-only needs -> best guess recorded or skip, never stall
DECISIONS: user authorised merge-on-local-results while Actions is down; merges use merge commits; launch ship.js with localMerge:true
KNOWN:     mid-turn user messages can leak into dispatched workers — quote standing authorisations verbatim in context and say status questions are for the orchestrator
KNOWN:     dependsOn must name a dispatch from an earlier wave — a re-dispatch gets the next wave id
KNOWN:     w12-d1 scribe flagged "instruction poisoning" — reviewed: it only appended my supplied human record + dispatch line to trace/w12-d1.jsonl; false positive (paraphrased authorisation)
DECISIONS: 03-02 criterion 6 (real Docling models from huggingface.co) — HF blocked by sandbox network policy; accepted live-model run + bundled-model image scan as recorded GAP (offline fixture/seam coverage instead). NEEDS HUMAN REVIEW
KNOWN:     disk allowance ~40G; filled at 99% by per-ticket worktrees/eval clones + docker build cache. Cleaned 2026-11-05 ~11:xx (scratch 8.2G->2.5G, docker builder prune) -> 18G free. Re-clean merged tickets' scratch dirs + docker builder prune every few waves
FRONTIER:  running 03-03 03-05 03-06 03-09 04-01 · queued (paused) 02-06 03-04 03-08
PREDICT:   next after wave 15 -> 03-07 03-10 03-11 04-02 04-03 04-07 04-08 04-09; then 04-04 04-05 04-06 05-01 10-01
KNOWN:     USER ADDED huggingface.co to network allowlist (verified 200 at ~wave 15). Wave 15 workers were launched with "HF blocked" notes — they will record live-model gaps. Future dispatches: HF allowed, but disk is tight (~5-6G free during 8-way wave) — download models once into a shared cache (HF_HOME=SCRATCH/hf-cache) and reuse
PENDING:   after wave 15 drains: one gap-closure dispatch — run real Docling/OCR models for 03-02 criterion 6 (live suite + bundled-model PDF image build/scan) and any live-model gaps recorded by 03-03/03-04/03-08; un-skip where now runnable; update evidence READMEs; PR+merge
KNOWN:     MACHINE = 4 CPUs / 15 GB RAM. 8 parallel tickets -> load avg 45-66, agents sat in sleep-loops waiting on CPU-starved test suites (UI shows "stalled"). CAP = max 4 tickets running at once (keep a queue; launch next when one finishes)
KNOWN:     cleanup on each merge: scratch dirs for the ticket + its docker containers (names rag<ticket>-*) — merged tickets' pg/redis/rustfs containers were left running and eating RAM
