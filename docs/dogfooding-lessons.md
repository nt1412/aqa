# Lessons from building AQA with AQA

A living record of what we learn by using AQA's own agent interface to build AQA.
Three audiences: **agents** using the platform, **humans** operating it, and
**future sessions** needing fast context recall. Each finding states what we hit,
why it matters, and the action (with status). Append as new lessons surface.

> Method: build each feature test-first, then drive AQA through its real front door
> (MCP / CLI / REST) to register the requirement and link coverage as tests land.
> Using the front door — not the back-door dogfood script — is what surfaces the
> gaps below. A script that calls services directly hides exactly the ergonomics an
> agent actually experiences.

---

## For agents using AQA

- **Cold-start identity only works over MCP.** `register_agent` (MCP) is open
  (enrollment-gated when auth is on); the REST/CLI `register-agent` requires an
  *existing* authenticated user, so it can't bootstrap. Onboard over MCP, then use
  the returned key for REST/CLI. *(Finding #2 — see backlog B1.)*
- **Register requirements up front; let coverage gaps be your worklist.**
  `get_coverage_gaps` lists requirements with no test. Create `REQ-*` when you start
  a feature; each gap closes when you link its test. The list *is* the plan.
- **Link coverage as tests land** with `link_coverage` (MCP) / `aqa req
  link-coverage` (CLI) — not only at requirement-creation time. *(Finding #1, fixed
  in T0.)*
- **Pass `branch` + `base_commit` on `record_test_run`** (`git merge-base HEAD
  <default-branch>`) so a branch's delta vs main resolves precisely. Without them,
  baseline resolution falls back to "latest main build before this one."
- **Check `get_case_history` before re-investigating a failure.** Its derived
  broke→fixed transitions are the *known regression path*: if this break was fixed
  before, the prior commit + reasoning are right there. Reading it costs ~nothing;
  re-deriving it costs an expensive model run.

## For humans operating AQA

- **Lineage turns opaque ids into commits.** `build-timeline` / `build-detail` /
  `case-history` replace raw `version_id`/`build_id` with commit SHAs, rollups, and
  per-case run history — the TestLink/TestRail-grade navigation that was missing.
- **Coverage gaps double as a planning board.** Requirements created before code
  show up as gaps immediately, so "what's planned but unbuilt" is queryable, not
  tribal knowledge.
- **Adding the MCP server mid-session isn't enough to *call* it.** `claude mcp list`
  shows it "Connected," but the model's tool registry only picks up a newly-added
  server after a **full client restart** (a soft `/mcp` reconnect refreshes health,
  not the callable tool set). The CLI/REST front door works immediately as a
  fallback.

## Engineering lessons (and product/test improvements)

- **The test harness builds schema with `Base.metadata.create_all`, not Alembic.**
  So any DB object that isn't an ORM table — views, functions, triggers — is absent
  in tests unless created separately. We solved it by putting view DDL in
  `app/db_views.py` and running it from **both** the migration and `conftest`.
  *Risk:* the next person adding a view will forget conftest. *(Backlog B2: consider
  running migrations to build the test schema so there's one path.)*
- **Centralize tricky definitions in one DB view.** `latest_result_per_build_case`
  encodes "the current result of a case in a build is its latest execution" once, so
  rollup / detail / diff / history can't disagree (a case run twice is never
  double-counted in one place and collapsed in another). The single biggest
  correctness lever in the lineage work.
- **MCP tool returns must be JSON-safe; REST's aren't a guide.** FastAPI serializes
  `datetime` automatically, but MCP tools returning plain dicts do not — we emit
  `created_at` as ISO strings in the service layer so both surfaces are safe.
  *(Backlog B3: a shared serialization helper for tool returns.)*
- **`alembic check` won't catch view drift.** Views aren't mapped models, so the
  migration-drift gate ignores changes to view bodies. View changes must be migrated
  deliberately; note this wherever views grow.

## Process lessons

- **Front-door dogfooding pays for itself in minutes.** Using MCP/CLI to fill in
  requirements surfaced two real ergonomic gaps (B1, and the now-fixed coverage-link)
  that the back-door script would never have shown. Build by *using* the surface.
- **The economic case is "avoided re-investigation."** A regression with a known
  path should never cost a second expensive (Opus/Fable) investigation. Features that
  surface known paths cheaply (case history, the guard) are measured in tokens saved,
  not rows recorded.

## Backlog discovered (product improvements)

| ID | Improvement | Source |
|----|-------------|--------|
| B1 | Allow agent cold-start over REST/CLI (enrollment-gated `register-agent` without a pre-existing user), matching MCP | Finding #2 |
| B2 | Build the test schema via Alembic migrations (or otherwise guarantee views/functions exist in tests) to remove the create_all-vs-migration trap | conftest view wiring |
| B3 | Shared JSON-serialization helper for MCP tool returns (datetimes, etc.) | lineage MCP tools |
| B4 | `projects.options['repo_url']` so commit SHAs render as clickable links in the console | spec deferral |
| B5 | Make the dogfood importer record via REST/MCP instead of calling services directly, so it exercises the real front door | dogfood scripts |

---

## Backlog status

All of B1–B5 are **resolved**, plus **B6** (added during the work):

- **B1 ✓** agent cold-start over REST/CLI via enrollment key (`auth.enrollment_allows`).
- **B2 ✓** `tests/test_migrations.py` proves the chain builds the full schema from scratch
  (kept create_all in the main suite — the full migration-based swap was judged not worth
  the risk for marginal gain over `alembic check` + this test).
- **B3 ✓** `_json_safe` for MCP tool returns.
- **B4 ✓** clickable commit links via `projects.options.repo_url`.
- **B5 ✓** both dogfood scripts record/backfill through REST (`scripts/_aqaclient`).
- **B6 ✓** `guard_hits` table → health reports `reinvestigations_avoided` (actual) beside
  `reinvestigations_avoidable` (point-in-time).

## Live validation findings (the thesis, finally exercised on real branch data)

The branch-aware centerpiece had only ever been proven by unit tests — every live
check showed `/branches` empty because all of AQA's own builds were on `main`.
Running a real regression on a real branch proved the loop (BLOCKED → quarantine →
READY) **and** surfaced two things unit tests can't:

- **A baseline must be a *representative full* build.** The latest default-branch
  build is the baseline, and a partial one (e.g. a smoke run that catalogued only
  one module) makes almost every case read as `new_test` → false **READY**. Lay a
  full main build before judging branches. *(Possible hardening: prefer the latest
  full build, or mark builds partial/complete.)*
- **Build identity is `(plan, build_name)`, and dogfood names builds by short SHA.**
  Two builds at the same SHA collide into one row — so a branch needs its **own
  commit** (distinct SHA) or its build merges into main's. Real branches have
  distinct commits, so this is fine in practice, but recorders must keep build
  names commit-unique and baselines must not share a name across branches.

## Changelog

- **2026-06-15** — Initial capture during the Operator Console lineage work (T0
  coverage-link, T1 lineage spine). See
  `docs/superpowers/specs/2026-06-15-operator-console-lineage-design.md`.
- **2026-06-15** — Backlog hardening: B1–B6 resolved (see above).
