# AQA Operator Console — Lineage, Health & Navigation Design

*Date: 2026-06-15*

## Context

AQA today is an agent-first backend with a thin supervision UI. It is **not** yet a
test-management product a human can *navigate* the way TestLink/TestRail can:

- **Navigation** — the suite browser is an always-expanded tree with no search/filter,
  and the case list shows each version's *design status*, not its **latest run result**.
  You cannot see "is this case green right now?" while browsing.
- **Health** — the dashboard is one flat tally across *all* plans/builds, with no time
  dimension, no per-build rollup, no "newly failing / newly passing / flaky."
- **Lineage** — executions render `version_id`/`build_id` as raw integers (`v94`, `b12`)
  with no commit SHA, no build detail, no build-to-build comparison.

Meanwhile the world this serves has changed: **many agents and developers each work on
their own branch/worktree**, new tests arrive constantly, and new functionality lands
constantly. Lineage is therefore **not a line** — it is a fan of concurrent branches,
each of which must be judged against where it forked from `main`.

The goal is to make AQA a navigable, health-aware, **branch-aware** operator console
where a human and an AI agent collaborate to **make regression hard** — and to do so in
a way that pays for itself in saved expensive-model tokens.

## North Star: a known regression path is a cached expensive answer

The value of AQA is not "we recorded that it broke." It is that **the first time an
expensive model (Opus, Fable) investigates a failure, that investigation is amortized
across every human and agent who would otherwise repeat it.** A regression with a known
path must never cost a second expensive investigation — human minutes *or* model tokens.

This turns a passive ledger into an active guard and dictates three design choices
threaded throughout this spec:

1. **Regression↔fix linkage** is surfaced (broke@commit → fixed@commit + the prior
   reasoning) — derived from the spine, ~no new storage.
2. **A known-regression guard** lets an agent ask, cheaply, "what is known to break on
   this branch / for these cases?" *before* burning tokens rediscovering it.
3. **The headline metric is "re-investigations avoided" (≈ tokens saved)**, not
   "executions recorded."

## Core principles

- **Compute-on-read, view-backed.** No materialization. Aggregations are regular
  Postgres **views** (zero storage, always correct, no `REFRESH`, no drift) plus
  parameterized service-layer queries that read from them. A materialized layer behind
  the same endpoint signatures is the escape hatch *if and only if* reads measurably
  slow down.
- **One definition of "current result," centralized.** A case can be executed multiple
  times in one build (re-runs, retries, cascade-blocks). Every rollup, diff, history,
  and dashboard must collapse to the **latest execution per (build, case)** — never
  count them all. This rule lives in exactly one view so no consumer can disagree.
- **Branch is an orthogonal attribute on the existing per-plan Build**, not a new spine.
  `Build` already carries `branch` and `commit_id`. The merge-readiness *verdict* is
  taken at the grain of `(branch, head-commit)` and **summed across every plan** that ran
  at that commit (see "Verdict grain" below) — a branch is judged by all its builds, not
  one. Minimal schema change.
- **Humans and agents share one work queue.** Collaboration actions (re-run requests)
  are `assignments`, which agents already discover via `list_assignments`/MCP. The human
  and the agent look at the *same* verdict and the *same* queue.
- **Verification stays test-driven.** Service-layer tests under savepoint isolation are
  the proof; the dogfood path records AQA's own runs so the views render real data live.
  No ad-hoc manual checks.

## Architecture

```
                    ┌─────────────────────────────────────────────┐
  Next.js UI  ◀────▶│  REST /api/v1   ·   MCP tools   ·   aqa CLI  │
  (operator)        └───────────────────────┬─────────────────────┘
                                             │ one service layer
                          ┌──────────────────┴───────────────────┐
                          │  lineage services (compute-on-read)   │
                          │  baseline resolution · diff · history │
                          │  rollup · branch health · guard       │
                          └──────────────────┬───────────────────┘
                                             │ SELECT from views
                    ┌────────────────────────┴────────────────────────┐
                    │  VIEW latest_result_per_build_case  (the rule)   │
                    │  VIEW build_rollup        (counts on top of it)  │
                    └────────────────────────┬────────────────────────┘
                                             │
                              PostgreSQL: builds · executions · ...
```

### The two views

**`latest_result_per_build_case`** — for each `(build_id, case_id)`, the single latest
execution (by `created_at`, tie-broken by `id`) and its status. This is the only place
the "collapse to latest" rule is expressed. Branch-agnostic, so it powers both
chronological compare and branch-vs-baseline compare with no extra machinery.

**`build_rollup`** — on top of the base view: per `build_id`, counts of
`pass/fail/blocked/not_run` and `pass_rate`. The `not_run` denominator is the set of
cases in the build's plan (`test_plan_cases`) that have **no** latest result in that
build.

Parameterized logic (build A↔B compare, branch↔baseline compare, case history, project
health trend, the known-regression guard) stays as **service-layer queries that filter
the views** — views cannot take parameters, and the A↔B diff is a self-join on two
specific build ids.

### Migrations (`CREATE OR REPLACE VIEW` in Alembic upgrades; `DROP VIEW` downgrades)

Hand-written SQL in the migration — no new dependency. (`alembic_utils` would add
autogen for replaceable entities, but two views do not justify it.) `alembic check`
migration-drift will not flag view bodies (views are not mapped models), so view changes
must be deliberately migrated — acceptable and documented.

## The lineage spine

A **Build = a run of one plan at a commit, on a branch.** The schema already supports
this: `builds.plan_id`, `builds.name`, `builds.commit_id`, `builds.branch`,
`builds.created_at` (via `TimestampMixin`). Builds are found-or-created by
`(plan_id, name)` at record time, with `commit_id`/`branch` backfilled once.

### Baseline resolution (branch → main)

To judge a branch build we diff it against a **baseline build on the project's default
branch**. Resolution is **precise with a time-based fallback**:

1. **Precise** — if the recorder supplies `base_commit` (agents/CI know it via
   `git merge-base HEAD <default_branch>`), the baseline is the default-branch build
   whose `commit_id == base_commit`, if one exists.
2. **Fallback** — otherwise the baseline is the latest default-branch build created at or
   before the branch build's `created_at`.
3. If neither resolves (no default-branch builds yet), the branch has **no baseline**;
   its delta is reported as "all results are new — no baseline to compare."

The project's default branch is stored in `projects.options['default_branch']` (JSONB,
defaults to `"main"`) — **no migration**.

### Verdict grain (avoids a false-green in the centerpiece)

A branch may touch **more than one plan** at the same commit (e.g. Smoke + Regression +
Security), producing several builds that share `(branch, commit_id)`. "Latest build per
branch" would arbitrarily pick one plan and ignore the others — a branch could read
**READY** because its Smoke build is green while its Regression build holds two
regressions the view never inspected. That is a false-green in the exact view whose job
is to make regression hard.

Therefore merge-readiness is computed at the grain of **`(branch, head-commit)`, summed
across all plans**:

1. Identify the branch's **head commit** — the most recent `commit_id` among its builds.
2. Take **every build** at `(branch, head-commit)` (one per plan that ran).
3. Run each through `compare?to=baseline` against *its own plan's* baseline.
4. **Sum** the per-plan deltas; the verdict is **BLOCKED** if *any* plan has a regression,
   **READY** otherwise. The UI shows the summed counts and expands to the per-plan breakdown.

This is a service-layer loop over the per-plan compare already being built — it needs no
new view and does **not** require the deferred project-wide commit-navigation lens.

### Diff classification (the part CI usually gets wrong)

Comparing a build against a baseline, each case in either side is classified as exactly
one of:

| Class | Baseline result | This build result | Meaning |
|---|---|---|---|
| **regression** | pass | fail/blocked | you broke it — **blocks merge** |
| **fixed** | fail/blocked | pass | you fixed it |
| **still_failing** | fail/blocked | fail/blocked | pre-existing, not your fault |
| **still_passing** | pass | pass | unchanged green |
| **new_test** | (none) | any | new coverage added on this branch |
| **removed** | any | (none) | case not run in this build |

Collapsing **regression** (green→red) and **new_test** (no baseline) — which look
identical in a naive diff — is the single most important correctness goal of this work.

## Data-model deltas (deliberately minimal)

**Phase 1**
- `builds.base_commit` — nullable `String(64)`. One migration. Stores the supplied
  merge-base so the precise baseline is reproducible after the fact.
- `projects.options['default_branch']` — JSONB key, no migration.
- Re-run requests — **no migration**: `assignments` already has `type`, `build_id`,
  `assigner_id`, `status`, `assignee_type`. A re-run is `type='rerun'`.

**Phase 2**
- `test_cases.quarantined` — nullable `Boolean`. One migration.
- `annotations` — small polymorphic table `(id, entity_type, entity_id, author_id, text,
  created_at)`, matching the codebase's existing polymorphic-junction pattern.

**Phase 3** — none (navigation reuses existing reads + the base view).

Regression↔fix linkage and known-paths need **no storage**: the fix commit is derived
from a case's red→green transition in history, and the reasoning is already in
`execution_reasoning`.

## API surface

### Phase 1 — reads (compute-on-read, view-backed)

| Endpoint | Returns | Powers |
|---|---|---|
| `GET /plans/{id}/builds` *(enriched)* | each build + `commit_id`, `branch`, `base_commit`, `created_at`, and its `build_rollup` (counts, `pass_rate`, total) | Build Timeline |
| `GET /builds/{id}` | build header + per-case latest results (case, version, status, exec id, duration) | Build Detail |
| `GET /builds/{id}/compare?to={build_id}` | classified diff (regression / fixed / still_failing / still_passing / new_test / removed) | chronological compare |
| `GET /builds/{id}/compare?to=baseline` | same diff vs the auto-resolved baseline | branch-vs-main compare |
| `GET /cases/{id}/history` | executions across builds, each with build name + `branch` + `commit_id` + status, chronological; plus derived `broke_at`/`fixed_at` commit pairs | Case Run History + sparkline + known path |
| `GET /projects/{id}/branches` | active branches (builds in a trailing window, excluding default branch); for each, all builds at its `(branch, head-commit)` summed across plans → delta-vs-baseline (regression count, fixed, new_test, coverage delta) + per-plan breakdown + merge-readiness verdict (BLOCKED if any plan regresses) | Branches / Merge-Readiness |
| `GET /projects/{id}/branches/{branch}/known-regressions` | open regressions on the branch, each annotated with its known fix-path if one exists (broke@commit → fixed@commit + prior reasoning excerpt) | known-regression guard |

### Phase 1 — writes (collaboration)

| Endpoint | Effect |
|---|---|
| `POST /builds/{id}/rerun` | create re-run `assignments` for all (or selected) cases in the build; idempotent — no duplicate *open* rerun for the same (case, build) |
| `POST /cases/{id}/rerun` | create a single re-run assignment carrying `build_id` + `branch` + `commit` context |

### MCP / CLI mirrors (Phase 1)

- `get_build_health(plan_id, build_id?)`, `compare_builds(build_id, to)`,
  `get_case_history(case_id)`, `list_branch_status(project_id)`,
  **`get_known_regressions(project_id, branch?, case_ids?)`** — the guard an agent calls
  before working.
- `request_rerun(case_id|build_id, assignee?)` — agents and humans file into the same
  queue; agents discover re-runs via the existing `list_assignments`.
- `record_test_run` gains optional `branch` and `base_commit` parameters (build already
  stores `branch`; `base_commit` is persisted on the build).
- CLI: `aqa build health`, `aqa build compare`, `aqa case history`,
  `aqa branch status`, `aqa branch known-regressions`, `aqa run rerun`.

## UI views

### Phase 1 — lineage (built on the existing app-router + `api` client + `ui.tsx` kit; new components `RollupBar`, `DiffTable`, `Sparkline`, `CommitRef`)

**① Build Timeline** (per plan) — chronological builds; each row: build name,
`CommitRef` (short SHA, links to remote if `projects.options['repo_url']` is set),
branch, relative time, and a `RollupBar` + `pass_rate`. Click → Build Detail. A
"compare ▾" affordance selects two builds.

**② Build Detail** `/builds/[id]` — header (name · commit · branch · time · rollup);
per-case latest-result table (case, status, exec→evidence, duration), filterable by
status. Actions: *request re-run of build*, per-row *re-run this case*.

**③ Build Compare / Diff** — regressions first and prominent, then fixed, still-failing,
new tests, removed. Each row links to the case's history + evidence. When `to=baseline`,
the header names the resolved baseline (`main @ 9f8e7d`, precise or fallback).

**④ Case Run History** — enriches `/cases/[id]` with a status `Sparkline` across builds
(hover = build + branch + commit + time) and a table. Surfaces flakiness visually
(`🟢🟢🔴🟢🔴🟢` at one commit) and shows the derived known path (broke@→fixed@).

**⑤ Branches / Merge-Readiness** (the centerpiece) — per active branch: head commit,
owner (agent/human), and the delta-vs-baseline **summed across every plan that ran at
that commit** (regressions introduced → **BLOCKED**, tests fixed, new tests added,
coverage delta → **READY**). Each row expands to the per-plan breakdown so a regression
in *any* plan is visible, never masked by another plan's green build. This is where a
human and an agent look at the *same* verdict before a merge. Re-run requests are issued
from here.

Commit SHAs replace raw `v94`/`b12` everywhere they currently leak (dashboard
recent-executions, etc.).

### Phase 2 — health
Project Health page: latest-build-per-plan cards, `pass_rate` trend sparkline, a
**regression panel** (open regressions across active branches), **flaky-candidates**
panel (cases that flip status across consecutive builds, especially at the same commit),
coverage health, and the **north-star metric** ("re-investigations avoided ≈ tokens
saved" — counted from known-regression-guard hits). Collaboration: **quarantine /
mark-flaky** (sets `test_cases.quarantined`; quarantined cases are pulled out of the
regression panel so they do not drown real signal) and **regression annotations**
(`annotations` table).

### Phase 3 — navigation
Suite browser upgrade: search, status/type/keyword filters, expand/collapse with
persisted state, breadcrumbs, and **latest run result + sparkline inline per case** (the
single biggest day-to-day improvement). Case-detail polish.

## Phasing

- **Phase 1 (the anchor) — branch-aware lineage spine.** Two views; the build/compare/
  history/branches/known-regressions endpoints; the five UI views; commit SHAs
  everywhere; re-run requests (UI + MCP/CLI); the known-regression guard.
  Schema delta: `builds.base_commit` (one migration); `default_branch` in options.
- **Phase 2 — health + token-saving metric.** Health page, regression/flaky panels,
  quarantine, annotations. Schema delta: `test_cases.quarantined`; `annotations` table.
- **Phase 3 — navigation.** Suite-browser search/filter/expand-collapse/breadcrumbs +
  inline latest-result. No schema delta.

## Testing & verification

Service-layer tests under the existing savepoint isolation are the proof. Required edges:

- **Latest-per-build-case collapse** — multiple executions of one case in a build resolve
  to the latest; rollup/diff/history all agree.
- **`not_run` denominator** — plan cases with no execution in a build count as not_run.
- **Diff classification** — regression vs new_test vs fixed vs still_failing vs removed,
  including the green→red vs no-baseline distinction.
- **Baseline resolution** — precise (`base_commit` match), fallback (latest-main-before),
  and no-baseline cases.
- **Re-run idempotency** — no duplicate open rerun for the same (case, build).
- **Known-regression guard** — returns a fix-path when a prior red→green exists; empty
  when none.
- **Cross-plan verdict grain** — a branch with a green build in plan A and a regressing
  build in plan B at the same head commit must read **BLOCKED**, not READY (no
  false-green from picking one plan's build).

MCP/CLI tests cover the new tool/command mirrors. The **dogfood path records AQA's own
runs across simulated branches**, so the lineage and Branches views render real AQA data
live — verification is test-driven, never ad-hoc.

## Edge cases

- Builds with no `commit_id` (older/manual runs) render `(no commit)` and are excluded
  from precise baseline resolution.
- A branch with no resolvable baseline reports "all results new" rather than flagging
  everything as a regression.
- `default_branch` builds compared to baseline compare against the *previous* default
  build (chronological), preserving the original main-line "what regressed" use.
- Quarantined cases (Phase 2) still appear in builds and history; they are only excluded
  from the regression *panel/verdict* so they do not mask new breakage.
- A case deleted/renamed across versions is tracked by `case_id`, not name, so history is
  stable.

## Intentional omissions

- **No materialized views / rollup tables** until reads measurably slow (escape hatch is
  swapping the view implementation behind the same endpoints).
- **No git topology in AQA** — merge-base is supplied by the recorder, not computed.
- **No "merged" detection from git** — a branch is "active" by recency; an explicit
  archive action can be added later if the branch list gets noisy.
- **Project-wide "commit X across all plans" *navigation* lens is deferred** — a
  first-class, browse-by-commit-across-plans view is presentation, not correctness. Note
  this is distinct from the *verdict aggregation* above, which IS in Phase 1: the
  merge-readiness verdict must sum per-plan deltas at `(branch, head-commit)` or it can
  false-green. The cross-plan *sum* ships in Phase 1; the cross-plan *browsable view*
  does not.

## Open questions

- **Repo links** — surfacing `CommitRef` as a clickable link needs
  `projects.options['repo_url']`; the format (GitHub/GitLab/Bitbucket path templates) can
  be a small config map. Not blocking Phase 1 (SHAs render as text without it).
- **Trailing window for "active branch"** — default 14 days; revisit if branches are
  long-lived.
