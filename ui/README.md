# AQA UI — "Mission Control"

A Next.js supervision console for the AQA backend. Phosphor-terminal dark
aesthetic (IBM Plex Mono/Sans, lime accent, status-as-color, grain+grid texture).

## Run

```bash
# 1. backend (from repo root)
docker compose up -d postgres minio
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed          # admin / admin
.venv/bin/uvicorn app.main:app --port 8000

# 2. UI (from ui/)
npm install
AQA_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

Log in with `admin` / `admin`. `next.config.mjs` proxies `/api/*` → the backend.

## Views

Design: Dashboard, Suites, Test Case Editor, Plans, Execution Runner, Requirements.
Supervision: Agent Activity Feed, **Evidence Viewer** (forensic split — reasoning,
artifacts, claims, similar failures), Claim Audit Board (kanban verify).
Insight: Traceability Matrix, Reports. System: Admin.

## Architecture

- `app/` — App Router pages; `(app)/` is the authenticated shell group.
- `components/ui.tsx` — the shared design-system primitives (the single source of
  visual truth; every view composes these).
- `components/Shell.tsx` — nav rail + top bar (project switcher).
- `lib/api.ts` — typed client for the full `/api/v1` surface; `lib/types.ts` mirrors
  the backend schemas; `app/providers.tsx` holds auth + current-project context.
- `app/globals.css` — design tokens (CSS variables) + texture + base styles.

## Build

```bash
npm run build      # all routes typecheck + compile
```
