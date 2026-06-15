# AQA

[![CI](https://github.com/nt1412/aqa/actions/workflows/ci.yml/badge.svg)](https://github.com/nt1412/aqa/actions/workflows/ci.yml)

**The system of record for agentic verification.** Your agents write code, your
tests verify it — AQA *remembers*, so nothing breaks twice.

AQA (pronounced "aqua") is test management built for the agentic coding loop — a
[TestLink](https://testlink.org)-equivalent that sits one layer above your test
runner and turns every verification into a durable, attributable, queryable
fact. Plans, cases, dependencies, run history, requirements-to-test
traceability, and a claim/verify protocol — all reachable by your **agents over
MCP**, not just humans in a dashboard. REST API + MCP server + CLI over one
service layer.

> It doesn't replace your tests. It makes them institutional.

---

## Why (coding agents are brilliant and amnesiac)

- **No regression memory.** An agent doesn't recall the bug it fixed last
  Tuesday; the same class of break gets reintroduced.
- **Green CI ≠ reliable software.** A passing pipeline tells you the tests that
  ran passed — nothing about the invariant nobody wrote a test for.
- **Agents mark their own homework.** One agent that writes the code, asserts the
  claim, and declares victory has no independent check.

## What it does

- **🔒 Regression ratchet** — every bug becomes a permanent test case, so "this
  broke once" can't silently come back. Your suite becomes accumulated memory.
- **🔦 Blind-spot radar** — `get_coverage_gaps` surfaces requirements with no
  test (and the backfill flags cases traced to no requirement), and self-heals so
  coverage can't silently drift.
- **👥 Doer ≠ checker** — a claim/verify protocol: the agent that does the work
  files a claim; a *different* agent (identity-enforced) confirms or refutes it.
- **⛓️ Dependency gating** — encode the real chain of your system; a downstream
  case can't report a meaningless "pass" when its prerequisite is broken.
  Cascade-blocking kills false green.

**Honest boundary:** AQA raises your *floor* (no silent regressions, no invisible
blind spots, no self-graded work). It does **not** raise your ceiling — it runs
no tests of its own and invents no correctness. The reliability gain is a
ratchet that compounds across commits and sessions, as long as your cases encode
real invariants and your checks actually run.

---

## Run it

```bash
cp .env.example .env
docker compose up -d postgres minio          # Postgres (+pgvector) and MinIO
pip install -e ".[dev]"
alembic upgrade head
python -m scripts.seed                        # admin / admin + default roles
uvicorn app.main:app --port 8000              # REST API  → http://localhost:8000/docs
AQA_MCP_TRANSPORT=streamable-http AQA_MCP_PORT=8001 \
  python -m app.mcp_server.server             # MCP server → http://localhost:8001/mcp
```

UI (optional supervision console): `cd ui && npm install && npm run dev`.

---

## Wire it into your coding agent

AQA is driven by **MCP** — point your coding agent at it and it self-onboards.
Full recipes (Claude Code, Cursor/Windsurf, generic MCP, CI) in
**[docs/integrating-with-agents.md](docs/integrating-with-agents.md)**; the short
version:

**1. Add AQA as an MCP server.** e.g. Claude Code:
```bash
claude mcp add --transport http aqa http://localhost:8001/mcp
```

**2. Tell your agent to use it.** Drop this into your project rules
(`CLAUDE.md` / `AGENTS.md` / `.cursorrules`):

> You have an `aqa` MCP server — the team's test-management + verification memory.
> - Call `register_agent` once, then read the `orientation` it returns.
> - **Before fixing a bug**, record it as a test case (`create_test_case`) so it
>   becomes a permanent regression check.
> - **After making a change**, run the relevant cases and `record_test_run`
>   (status + your `commit_id`). Don't claim "done" until it's recorded.
> - When you assert something works, file it as a `claim` on the run — a separate
>   auditor agent will `verify_claim` it. Don't verify your own claims.
> - Periodically check `get_coverage_gaps` and write tests for what's untested.

**3. (Optional) run a second auditor agent** that polls
`list_unverified_claims` → `verify_claim` — independent confirmation, enforced by
identity.

**4. From CI**, record results so runs are attributable across the team:
```bash
aqa run record <case_id> --plan <plan_id> --build "$GIT_SHA" --status pass --commit "$GIT_SHA"
```

The agent's loop becomes: **register → create_project → author cases →
plan + dependencies → run + record → self-correct → audit** — 29 MCP tools, all
mirrored in the `aqa` CLI. See **[docs/agent-guide.md](docs/agent-guide.md)**.

---

## CLI

```bash
aqa agent register --login my-bot --model claude-opus-4-8
aqa project create "Demo" --prefix DEMO
aqa plan manifest <plan_id>        # the ordered, dependency-gated run list
aqa req gaps <project_id>          # blind-spot radar
```

## Auth (opt-in)

The MCP layer is open by default. Set `AQA_MCP_REQUIRE_AUTH=true` to require a
valid `X-API-Key` (an agent key from `register_agent`) on every tool except
`register_agent`, which then requires the operator's enrollment secret
`AQA_MCP_ENROLL_KEY` as an `X-Enroll-Key` header (open registration would
otherwise mint keys to anyone; it fails closed). The authenticated identity
drives attribution; deactivating an identity revokes access.

## Tests · Contributing · License

```bash
pytest -q          # ~177 tests; 2 skip without live MinIO/embeddings
```

See [CONTRIBUTING.md](CONTRIBUTING.md) (logic lives in the transport-agnostic
`app/services/`; changes are test-driven; `ruff check .` must pass).
[Apache License 2.0](LICENSE) © 2026 Nishant Tiwari.
