# Contributing to AQA

Thanks for your interest in improving AQA. This project is a TestLink-equivalent
test-management platform built as an evidence and context store for AI QA teams.
Contributions — bug reports, features, docs — are welcome.

## Development setup

```bash
cp .env.example .env
docker compose up -d postgres minio
pip install -e ".[dev]"          # add [embeddings] for semantic failure search
alembic upgrade head
python -m scripts.seed           # admin/admin + default roles
uvicorn app.main:app --reload
```

UI (optional): `cd ui && npm install && npm run dev`.

## Architecture in one paragraph

REST API (FastAPI), MCP server, and CLI all sit on **one transport-agnostic
service layer** (`app/services/`). Services never import FastAPI and raise domain
errors from `app/services/errors.py`; routers and MCP tools are thin wrappers.
Add behavior in the service layer first, then expose it through the relevant
transport(s). The MCP server (`app/mcp_server/server.py`) is the curated agent
hot-path; the CLI (`cli/`) is a thin wrapper over REST.

## Ground rules

- **TDD.** Write a failing test, make it pass, keep it. Tests live in `tests/`
  and use savepoint-based isolation (each test rolls back).
- **Lint clean.** `ruff check .` must pass.
- **Keep transports thin.** Logic goes in `app/services/`, not in routers or tools.
- **Migrations.** Model changes need an Alembic migration (`alembic revision --autogenerate`).
- **Small, focused commits** with clear messages.

## Running checks

```bash
ruff check .
pytest -q                        # ~130 tests; 2 skip without live MinIO/embeddings
```

## Submitting changes

1. Fork and branch from `main`.
2. Make your change with tests; ensure `ruff` and `pytest` are green.
3. Open a pull request describing the change and how you verified it.

By contributing, you agree that your contributions are licensed under the
project's [Apache License 2.0](LICENSE).
