# AQA

[![CI](https://github.com/nt1412/aqa/actions/workflows/ci.yml/badge.svg)](https://github.com/nt1412/aqa/actions/workflows/ci.yml)

Test management for agentic coding — TestLink-equivalent, with a REST API, an MCP server, and a CLI over one shared service layer.

## Quick start

```bash
cp .env.example .env
docker compose up -d postgres minio
pip install -e ".[dev]"
alembic upgrade head
python -m scripts.seed          # creates admin/admin + default roles
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Get an API key (for agents/CLI)

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"login":"admin","password":"admin"}' | jq -r .access_token)
KEY=$(curl -s -X POST localhost:8000/api/v1/auth/token \
  -H "authorization: Bearer $TOKEN" | jq -r .api_key)
export AQA_API_KEY=$KEY AQA_API_URL=http://localhost:8000
```

## CLI

```bash
aqa project create "Demo" --prefix DEMO
aqa suite create 1 --name "Auth"
aqa case create 1 --from-file case.json
aqa run record 1 --plan 1 --build b1 --status pass
```

## MCP server

```bash
python -m app.mcp_server.server   # stdio transport
```

**Building tests with an agent?** See [docs/agent-guide.md](docs/agent-guide.md) —
the recommended workflow (register → discover → plan → run → self-correct →
audit) across the 28 MCP tools and the matching CLI.

**Per-agent MCP auth (opt-in).** The MCP layer is open by default. Set
`AQA_MCP_REQUIRE_AUTH=true` to require a valid `X-API-Key` (an agent key from
`register_agent`) on every tool except `register_agent`, which then requires the
operator's enrollment secret `AQA_MCP_ENROLL_KEY` as an `X-Enroll-Key` header
(open registration would otherwise mint keys to anyone; it fails closed). The
authenticated identity drives attribution (a passed `agent_id` can't override
it), and deactivating an identity revokes its access.

## Tests

```bash
pytest -v
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: logic lives in the
transport-agnostic service layer (`app/services/`), changes are test-driven,
and `ruff check .` must pass.

## License

[Apache License 2.0](LICENSE) © 2026 Nishant Tiwari.
