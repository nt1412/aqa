# AQA — Guide for QA Agents

How an autonomous QA agent uses AQA to author tests, run regressions, and
keep its work attributable and self-correcting. Read the **What's new** section
if you've used AQA before; then follow **Recommended workflow**.

---

## What's new (changelog for returning agents)

If your last run only created suites/cases and recorded a few executions, here's
what changed — all additive, nothing you did breaks:

- **Identity & provenance.** New `register_agent` tool/endpoint. Register once,
  then pass the returned **id** as `agent_id` to `record_test_run` so your runs
  are attributable (show up in `get_agent_execution_history`). Previously runs
  recorded with no tester were anonymous.
- **Test hierarchy & ordering.** `get_suite_tree`, `create_test_plan`,
  `add_cases_to_plan`, `add_test_dependency`, `get_run_manifest`. You can now
  discover the suite tree, build a prioritized run list, and declare
  prerequisites between cases.
- **Dependency gating.** `get_run_manifest` returns `depends_on`, `blocked_by`,
  and `runnable` per case. A case is blocked until its prerequisites pass.
- **Per-build gating.** `get_run_manifest(plan_id, build_id)` scopes gating to a
  single build — a prerequisite that passed in an older build does NOT count.
- **Cascade.** `record_test_run(..., cascade_blocked=true)` (default on) auto-
  records `blocked` for downstream cases in the same plan+build when a
  prerequisite fails — so the run reflects what can't be trusted. Never
  overrides a result already recorded for that build.

MCP surface is **28 tools** (incl. `create_project`, `list_agents`,
`deactivate_agent`). The CLI mirrors all of this, and per-agent MCP auth is
available opt-in (see below).

---

## Connect (MCP)

```
streamable-http: http://localhost:8001/mcp
```
Tools are self-describing — list them on connect. The DB (Postgres) must be up.

**Auth (opt-in).** By default the MCP layer is open. If the operator sets
`AQA_MCP_REQUIRE_AUTH=true`:
- every tool except `register_agent` requires a valid **`X-API-Key`** header
  (your own key from `register_agent`) — send it on every call;
- `register_agent` itself requires the operator's **enrollment secret** as an
  **`X-Enroll-Key`** header (`AQA_MCP_ENROLL_KEY`) — otherwise open
  registration would mint a key to anyone and defeat auth. It fails closed (no
  secret configured ⇒ no registration);
- your authenticated identity drives attribution — a passed `agent_id`/
  `auditor_id` can't override it (anti-spoof); deactivated identities can no
  longer authenticate.

So an enrolled agent: connect with `X-Enroll-Key` → `register_agent` → reconnect
with your returned key as `X-API-Key` → work.

## Connect (REST/CLI)

```bash
export AQA_API_URL=http://localhost:8000
export AQA_API_KEY=<your agent key>     # from `agent register`, below
aqa --help
```

---

## Recommended workflow

1. **Register once** → get your `agent_id`, a one-time API key, and an
   **`orientation`** payload (this workflow, returned in-band — read it).
   - MCP: `register_agent(login, agent_model)` → `{id, api_key, orientation, ...}`
   - CLI: `aqa agent register --login l33tpwn-regression --model claude-opus-4-8`
   - Self-onboarding: a project's coding agent registers itself this way.

1b. **Create your project if it's new** → `create_project(name, prefix)` (MCP)
   or `aqa project create <name> --prefix <PREFIX>`. The prefix is permanent
   and unique. Reuse the returned `project_id` everywhere below. (Skip if the
   project already exists — just use its id.)
   - Cache the **id**; the MCP hot path only needs the integer id. The api_key
     matters only for REST/CLI. Re-running after a DB reset → new id; re-register.

2. **Discover** what exists before creating (avoid duplicates).
   - `get_suite_tree(project_id)` — nested suites + per-suite case counts
   - `search_test_cases(project_id, query)`

3. **Author** (during requirements analysis / guardrail design).
   - `create_test_suite(project_id, "Purple/IPS Inline")` (find-or-create by path)
   - `create_test_case(...)` / `bulk_create_test_cases(...)`
   - `create_requirement(spec_id, ...)` and link coverage for traceability

4. **Plan** the run.
   - `create_test_plan(project_id, name)` → plan_id
   - `add_cases_to_plan(plan_id, case_ids, urgency)` (1=low, 2=med, 3=high)
   - `add_test_dependency(case_id, depends_on_case_id)` for prerequisites
     (e.g. recon → SQLi → RCE → privesc → persistence)

5. **Run** top-down off the manifest.
   - `get_run_manifest(plan_id, build_id?)` → ordered list with `runnable` /
     `blocked_by`. Run entries where `runnable=true`; for `runnable=false`,
     record them blocked citing `blocked_by` (or rely on cascade).
   - `record_test_run(case_id, plan_id, build_name, status, agent_id=<you>,
     commit_id=<sha>, claims=[...], reasoning={...}, cascade_blocked=true)`
   - Put the SHA in `commit_id` and a per-commit `build_name` (e.g.
     `regression-<shortsha>`) so "what regressed between builds" is answerable.

6. **Self-correct** on failure.
   - `get_failure_context(case_id)`, `search_similar_failures(case_id)`
     (semantic search needs the `[embeddings]` extra installed; otherwise
     structural context only).

7. **Audit** (as an auditor agent).
   - `list_unverified_claims(project_id)` → `verify_claim(claim_id, verdict,
     reasoning)` → `create_audit_report(...)`. Verdicts are an append-only
     trail; re-verifying overrides (history kept).

---

## MCP tools (28)

**Identity** — `register_agent`, `list_agents`, `deactivate_agent`
**Onboarding & authoring** — `create_project`, `create_test_suite`,
`create_test_case`, `bulk_create_test_cases`, `get_test_case`, `search_test_cases`
**Hierarchy & planning** — `get_suite_tree`, `create_test_plan`,
`add_cases_to_plan`, `add_test_dependency`, `get_run_manifest`
**Reporting** — `record_test_run`, `upload_artifact`
**Self-correction** — `get_failure_context`, `search_similar_failures`,
`get_agent_execution_history`
**Audit** — `get_execution_evidence`, `list_unverified_claims`, `verify_claim`,
`create_audit_report`, `evaluate_test_case`
**Coverage & assignment** — `get_coverage_gaps`, `create_requirement`,
`assign_test`, `list_assignments`

## CLI (mirrors the above)

```bash
aqa agent register --login <handle> --model <model>
aqa agent list
aqa agent deactivate <user_id>
aqa project create <name> --prefix <PREFIX>
aqa suite tree <project_id>
aqa plan create <project_id> --name <name>
aqa plan add-case <plan_id> --case <case_id> --urgency 3
aqa case depends <case_id> --on <prereq_case_id>
aqa plan manifest <plan_id> [--build <build_id>]
aqa run record <case_id> --plan <plan_id> --build <name> --status <s> \
    --commit <sha> --cascade
aqa req gaps <project_id>
aqa req traceability <project_id>
```

---

## Key behaviors to rely on

- **Attribution:** always pass `agent_id` to `record_test_run` (MCP) — REST/CLI
  infer it from your API key.
- **Build upsert:** `record_test_run` finds-or-creates the build by
  (plan, build_name); no separate build call needed. `commit_id` backfills once.
- **Gating is advisory + cascade:** the manifest tells you what's blocked;
  cascade auto-records downstream blocks on failure. Neither overrides a real
  recorded result.
- **Idempotency:** `create_test_suite` (by path), `add_cases_to_plan`,
  `add_test_dependency`, and coverage links are safe to re-run.
