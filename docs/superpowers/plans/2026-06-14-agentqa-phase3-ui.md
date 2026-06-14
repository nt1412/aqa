# AgentQA Phase 3 — Supervision UI

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax. The design system in this doc is the single source of truth — every view composes the shared primitives and tokens; do NOT invent per-view styles.

**Goal:** A distinctive, production-grade Next.js web UI for humans to supervise an AI QA team, talking to the existing FastAPI backend (`/api/v1`).

**Design identity — "Mission Control":** a phosphor-terminal industrial dark interface. Deep cool-slate canvas, hairline borders, a restrained lime/phosphor accent, and **status as a first-class visual language**. Typography: **IBM Plex Mono** (labels/data/headings, uppercase + tracked) + **IBM Plex Sans** (body). Subtle grain + grid texture; staggered panel reveals; the Evidence Viewer as a forensic split.

**Tech Stack:** Next.js 15 (App Router) + TypeScript + Tailwind CSS v4 + Framer Motion. Client-side data fetching via a typed `lib/api.ts` against `/api/v1` (proxied to the backend in dev). Auth: login → JWT, stored client-side; an API key can also be pasted.

---

## Design System (single source of truth)

**Color tokens (CSS variables, dark theme):**
```
--bg:        #0a0d12   (near-black cool slate canvas)
--bg-elev:   #11151c   (raised panels)
--bg-elev-2: #161b24   (nested/hover)
--border:    #222a36   (hairline)
--border-bright: #2e3947
--text:      #e6edf3   (primary)
--text-dim:  #8b98a9   (secondary/labels)
--text-faint:#5a6675   (tertiary)
--accent:    #b8f135   (phosphor lime — primary actions, active nav, logo)
--accent-dim:#7f9e2a
--pass:      #34d399   (emerald)
--fail:      #fb7185   (rose)
--blocked:   #fbbf24   (amber)
--not-run:   #64748b   (slate)
--in-progress:#38bdf8  (cyan)
--confirmed: #34d399  --refuted: #fb7185  --inconclusive: #fbbf24
```

**Type:** IBM Plex Mono (`--font-mono`) for headings/labels/data/badges (uppercase, letter-spacing 0.08em on labels); IBM Plex Sans (`--font-sans`) for prose/inputs. Loaded via `next/font/google`.

**Texture:** a fixed full-viewport overlay combining (a) a faint 1px grid (`linear-gradient` repeating, ~2% opacity) and (b) SVG fractal-noise grain (~3% opacity), `pointer-events:none`, behind content. Panels use hairline `--border` with a subtle top highlight.

**Motion:** Framer Motion staggered fade/translate on panel mount (`staggerChildren`); status dots pulse for `in_progress`/active; row hover lifts background to `--bg-elev-2`.

**Shared primitives (`components/ui/`):** `Panel` (titled bordered surface w/ uppercase mono header), `StatusBadge` (status→color+dot), `VerdictBadge`, `Button` (primary=lime, ghost, danger), `DataTable` (mono headers, hairline rows, hover), `Stat` (big mono number + label), `Field`/`Input`/`Textarea`/`Select`, `Tabs`, `EmptyState`, `Spinner`, `Tag`. All consume the CSS tokens.

**Layout shell (`components/Shell.tsx`):** fixed left nav rail (~64px collapsed icon rail or ~220px with labels) listing the views, grouped: *Design* (Dashboard, Suites, Plans, Requirements), *Supervision* (Activity, Evidence, Claims), *Insight* (Traceability, Reports), *Admin*. Top bar: project switcher (mono), current user, API status dot. Content area scrolls; nav fixed.

---

## File Structure

```
ui/
  package.json, tsconfig.json, next.config.mjs, postcss.config.mjs, .env.local.example
  app/
    globals.css            # tokens, fonts, grain/grid, base element styles
    layout.tsx             # fonts + <body> + texture overlay
    providers.tsx          # auth context, project context, query cache
    login/page.tsx
    (app)/layout.tsx       # Shell (nav + topbar); guards auth
    (app)/page.tsx                       # Project Dashboard
    (app)/suites/page.tsx                # Test Suite Browser
    (app)/cases/[id]/page.tsx            # Test Case Editor
    (app)/plans/page.tsx                 # Test Plan Manager
    (app)/runner/[executionId]/page.tsx  # Execution Runner (manual)
    (app)/requirements/page.tsx          # Requirements Manager
    (app)/traceability/page.tsx          # Traceability Matrix
    (app)/reports/page.tsx               # Reports
    (app)/activity/page.tsx              # Agent Activity Feed
    (app)/evidence/[caseId]/page.tsx     # Evidence Viewer
    (app)/claims/page.tsx                # Claim Audit Board
    (app)/admin/page.tsx                 # Admin
  components/Shell.tsx, components/ui/*.tsx
  lib/api.ts               # typed fetch client (+ all endpoint fns)
  lib/auth.ts              # token storage + context
  lib/types.ts             # TS types mirroring the API schemas
```

**Backend contract (key endpoints the UI calls):** `POST /api/v1/auth/login`, `/auth/token`, `/auth/me`; `GET/POST /projects`, `/projects/{id}/suites`, `/suites/{id}/tree`, `/suites/{id}/cases`, `/cases/{id}`, `/cases/{id}/versions`, `/cases/{id}/executions`, `/cases/{id}/evidence`, `/cases/{id}/failure-context`, `/cases/{id}/similar-failures`; `/projects/{id}/plans`, `/plans/{id}/builds|cases|milestones`, `/plans/{id}/executions`; `POST /executions`; `/executions/{id}/artifacts`; `/claims/unverified`, `/claims/{id}/verify`; `/projects/{id}/req-specs`, `/req-specs/{id}/requirements`, `/requirements/{id}/coverage`, `/projects/{id}/traceability`, `/projects/{id}/coverage-gaps`; `/agents/{id}/executions`; `/projects/{id}/platforms`, `/assignments`.

---

## Tasks

### Task 1 — Scaffold + design system foundation (controller-built)
Next.js app, Tailwind v4, fonts, `globals.css` tokens + grain/grid, `lib/api.ts` + `lib/auth.ts` + `lib/types.ts`, `next.config` API proxy, all `components/ui/*` primitives, `components/Shell.tsx`, login page, `(app)/layout.tsx` guard. Verify `npm run build` + typecheck pass.

### Task 2 — Project Dashboard (`(app)/page.tsx`)
Plan progress bars by build, pass/fail/blocked Stat tiles, recent execution activity feed, open assignments. Pulls `/projects`, `/plans`, `/plans/{id}/executions`.

### Task 3 — Test Suite Browser + Test Case Editor
Browser: suite tree (left) + case list (right), filterable. Editor: version + steps table, version history, script link, attachments; create-version action.

### Task 4 — Test Plan Manager + Execution Runner
Plan: cases grouped by suite, builds, milestones, add-case. Runner: step-by-step manual pass/fail/blocked with per-step notes → `POST /executions`.

### Task 5 — Requirements Manager + Traceability Matrix
Requirements: spec tree + requirement list + coverage status. Matrix: requirements × cases grid (covered/gap), from `/traceability` + `/coverage-gaps`.

### Task 6 — Agent Activity Feed + Evidence Viewer + Claim Audit Board (the supervision trio — richest)
Activity: real-time-ish feed of agent executions (agent, case, status, claim/artifact counts), filterable. Evidence Viewer: forensic split — steps+results left; tabs (Reasoning timeline, Artifacts, Claims w/ verification, Provenance) right; prior executions + similar failures. Claim Board: kanban (Unverified | Confirmed | Refuted | Inconclusive), verify action.

### Task 7 — Reports + Admin
Reports: coverage/progress/failure-analysis/agent-performance with mono charts (lightweight, CSS/SVG). Admin: users, API keys, platforms, keywords, integrations, audit log.

### Task 8 — Final polish + build verification + screenshots
`npm run build` clean, typecheck clean, Playwright screenshots of the hero views against a live backend + seeded data, README for the UI.

Each view: builds, is responsive-ish (desktop-first), composes ONLY shared primitives + tokens, and handles loading/empty/error states via `Spinner`/`EmptyState`.
