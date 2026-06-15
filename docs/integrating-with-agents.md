# Wiring AQA into your coding flow

AQA is reachable three ways over one service layer — **MCP** (for agents), **REST**
(`/api/v1`, docs at `/docs`), and the **`aqa` CLI** (for Bash-tool agents and CI).
For the agentic loop, MCP is the hot path. This guide shows how to connect popular
clients, what to tell your agent, and how to record from CI.

> New here? Read **[agent-guide.md](agent-guide.md)** for the full tool surface and
> the register → plan → run → audit workflow. The orientation is also returned
> in-band by `register_agent` (and readable openly via `get_orientation`).

---

## 1. Connect an agent over MCP

Two transports:

- **streamable-http** — one long-lived server many agents/humans share (recommended
  for a team). Start it:
  ```bash
  AQA_MCP_TRANSPORT=streamable-http AQA_MCP_PORT=8001 python -m app.mcp_server.server
  # → http://localhost:8001/mcp
  ```
- **stdio** — the client spawns AQA per session (no running server needed). Good for
  a single local agent.

### Claude Code
```bash
# http (shared server, must be running)
claude mcp add --transport http aqa http://localhost:8001/mcp

# or stdio (client spawns it)
claude mcp add aqa -- bash -lc 'cd /path/to/aqa && AQA_MCP_TRANSPORT=stdio python -m app.mcp_server.server'
```

### Cursor / Windsurf / Claude Desktop / generic MCP client
Add to the client's MCP config (e.g. `~/.cursor/mcp.json`, `claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "aqa": { "type": "streamable-http", "url": "http://localhost:8001/mcp" }
  }
}
```
stdio variant:
```json
{
  "mcpServers": {
    "aqa": {
      "command": "python",
      "args": ["-m", "app.mcp_server.server"],
      "cwd": "/path/to/aqa",
      "env": { "AQA_MCP_TRANSPORT": "stdio" }
    }
  }
}
```

On connect the agent can call `get_orientation` (open, no auth) to learn the
workflow, then `register_agent` to get its identity.

---

## 2. Tell your agent to use it (project rules)

The connection only makes the tools *available*. To make AQA part of the loop, add
a block like this to your coding agent's instructions — `CLAUDE.md`, `AGENTS.md`,
`.cursorrules`, or a system prompt:

```markdown
## Verification with AQA (the team's test-management memory)

You have an `aqa` MCP server. Use it to make your verification durable and checkable.

- Once per session: `register_agent(login=..., agent_model=...)`, then follow the
  `orientation` it returns. Reuse the returned id as `agent_id`.
- If this is a new project, `create_project(name, prefix)` and reuse its id.
- **Before fixing a bug:** capture it as a test case (`create_test_case`) under a
  meaningful suite. A fixed bug with no case will come back — encode it so it can't.
- **After any change:** run the relevant cases and `record_test_run` with the real
  `status`, your `commit_id`, and a per-commit `build_name`. "Done" means recorded.
- **Don't fake green:** if a case can't run (needs an env you don't have), record it
  `blocked`, not `pass`.
- **Claims you can't self-verify:** when you assert an invariant holds, attach it as
  a `claim` on the run. A separate auditor will confirm/refute it — do not verify
  your own claims.
- **Find blind spots:** check `get_coverage_gaps(project_id)` and write tests for
  untested requirements.
- **Encode prerequisites:** use `add_test_dependency` so a downstream case is gated
  on its prerequisite (a "pass" downstream of a broken prereq is a lie).
```

Tune to your stack; the point is that *recording in AQA is part of "done,"* not an
afterthought.

---

## 3. The doer ≠ checker pattern

Run a second, separate agent as the **auditor** so verification is independent:

```
loop:
  claims = list_unverified_claims(project_id)
  for c in claims:
      verdict = <independently check c.claim_text against the evidence>
      verify_claim(c.id, verdict, reasoning)   # confirmed | refuted | inconclusive
```

Because the auditor registers as its own identity (and, with auth on, the
authenticated identity drives attribution), the checker is provably not the doer.

---

## 4. Record from CI

Your pipeline already runs tests; have it record the results into AQA so history is
attributable across humans and agents. Map each test to a case once, then:

```bash
export AQA_API_URL=http://localhost:8000
export AQA_API_KEY=<an agent key from `aqa agent register`>

aqa run record <case_id> \
  --plan <plan_id> --build "$GIT_SHA" --status "$STATUS" \
  --commit "$GIT_SHA" --cascade
```

`--build` upserts by (plan, name); `--commit` backfills the SHA so "what regressed
between builds" is answerable; `--cascade` auto-blocks downstream cases when a
prerequisite fails. (See `scripts/dogfood.py` for a JUnit-XML → AQA importer — AQA
catalogs its *own* pytest suite into itself this way.)

---

## 5. Auth in shared/production setups

By default the MCP layer is open (fine for a trusted local loop). For a shared
server, enable per-agent auth:

```bash
AQA_MCP_REQUIRE_AUTH=true AQA_MCP_ENROLL_KEY=<join-secret> \
AQA_MCP_TRANSPORT=streamable-http python -m app.mcp_server.server
```

Then agents send `X-API-Key: <their key>` on every call, and **registration**
requires `X-Enroll-Key: <join-secret>` (so open registration can't mint keys).
Revoke an agent with `deactivate_agent` / `aqa agent deactivate <id>`.

---

## What you get

The longer your agents work against AQA, the more your suite becomes the accumulated
memory of everything that ever went wrong — a reliability ratchet that compounds per
commit, per session, per agent. AQA doesn't run your tests or invent correctness; it
makes the verification you already do durable, attributable, and impossible to fake.
