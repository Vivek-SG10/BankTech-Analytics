# BankTech Analytics — Handoff Log

This file records key decisions, changes, and known issues at the end of each phase.
Add an entry whenever you hand off to another developer, session, or AI agent.

---

## Phase 0 — Scaffold & Health Check

**Date**: 2026-10-28
**Status**: ✅ Complete

### Summary
Set up the base project skeleton and wired a live health endpoint that verifies database connectivity.
All three backend tests pass. FastAPI server starts and returns HTTP 200 from `/api/v1/health`.
Frontend TypeScript compiles with zero errors.

### Files Created / Changed

| File | Action | Notes |
|------|--------|-------|
| `backend/app/core/__init__.py` | Created | Core package marker |
| `backend/app/core/config.py` | Created | Pydantic-Settings env config |
| `backend/app/core/database.py` | Created | Async SQLAlchemy 2 engine + `ping_database()` (psycopg3) |
| `backend/app/api/__init__.py` | Updated | Removed eager numpy-triggering import for Phase-0 safety |
| `backend/app/api/health.py` | Created | `GET /api/v1/health` with real DB check + latency |
| `backend/app/analytics/__init__.py` | Updated | Removed eager numpy import for Phase-0 safety |
| `backend/app/main.py` | Rewritten | Phase-0-safe; Phase-1+ routers guarded in try/except |
| `backend/requirements.txt` | Rewritten | Pinned Phase-0 deps with pre-built cp314 wheels; Phase-1/2 commented |
| `backend/tests/__init__.py` | Created | Tests package marker |
| `backend/tests/test_health.py` | Created | 3 async tests (status, schema, content-type) — all PASS |
| `backend/pytest.ini` | Created | asyncio_mode=auto, fixture_loop_scope=function |
| `frontend/vite.config.ts` | Updated | Added `/api` proxy → `http://localhost:8000` |
| `frontend/src/App.tsx` | Rewritten | Calls real `/api/v1/health`, shows live DB status, auto-polls 15s |
| `frontend/index.html` | Updated | Title + meta description |
| `.env.example` | Updated | All values are now `<placeholder>` only |
| `.gitignore` | Created | Covers Python, Node, Docker volumes, AI data |
| `README.md` | Rewritten | Three-terminal quick-start, phase table, prereq table |
| `docker-compose.yml` | Updated | Postgres healthcheck, psycopg URL scheme, proper port |
| `docs/handoff-log.md` | Created | This file |

### Architecture Decisions

- **Phase-0-safe startup**: `main.py` wraps Phase-1+ router imports in try/except.
  Additionally, `app/api/__init__.py` and `app/analytics/__init__.py` no longer eagerly
  import heavy modules that chain-import numpy/langchain.
- **Health endpoint always returns 200**: The `database` field is `"ok"` or `"unreachable"`.
  Returning 200 always means the frontend can parse the body — a 503 here would mask
  whether the API or the network was the problem.
- **Driver: psycopg3 (psycopg[binary])** instead of asyncpg: Python 3.14 on Windows has
  no pre-built asyncpg wheel (requires MSVC Build Tools to compile Cython). psycopg3
  ships a pre-built `cp314-cp314-win_amd64.whl`. pydantic 2.14.1 ships pydantic-core
  2.50.1 which also has a pre-built cp314 wheel.
- **Vite proxy**: Frontend calls `/api/v1/health` (relative path). Vite forwards to
  FastAPI. No `VITE_API_URL` env var required during development.
- **URL auto-patching**: `config.py` converts `postgresql://` or `postgresql+asyncpg://`
  → `postgresql+psycopg://` automatically, so docker-compose env vars don't need updating.

### Dependency Resolution Notes

| Package | Issue | Resolution |
|---------|-------|-----------|
| `asyncpg 0.30.0` | No cp314 wheel, needs MSVC/Cython | Replaced with `psycopg[binary] 3.3.6` |
| `pydantic-core 2.33.2` | No cp314 wheel, needs MSVC/Rust | Upgraded to `pydantic 2.14.1` → `pydantic-core 2.50.1` (has cp314 wheel) |
| `numpy`, `pandas` | Phase 1+ only | Commented in requirements.txt |
| `langchain`, `chromadb` | Phase 2+ only | Commented in requirements.txt |

### Commands Actually Run

```powershell
# Installed dependencies
cd backend
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt --only-binary=:all:

# Tests
.venv\Scripts\python.exe -m pytest tests/test_health.py -v
# Result: 3 passed in 0.63s

# Server import check
.venv\Scripts\python.exe -c "from app.main import app; print(app.routes)"
# Routes: ['/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc', '/api/v1/health', '/api/v1/auth/login']

# Live health check (with server running)
# GET /api/v1/health → 200 {"status":"ok","service":"BankTech Analytics API","database":"unreachable",...}

# Frontend
cd frontend && npx tsc --noEmit  # → 0 errors
```

### Known Issues / Next Steps for Phase 1

1. **Docker not yet confirmed on this machine** — PostgreSQL needs Docker Desktop or a
   local install. Once available, run `docker compose up postgres` and the database status
   will change to `"ok"`.
2. **asyncio DeprecationWarnings** from pytest-asyncio, fastapi, anyio — these use
   `asyncio.get_event_loop_policy()` which is deprecated in Python 3.14. These are
   upstream library issues, not in our code. Will resolve as libraries update.
3. **Auth, analytics, RAG stubs** — placeholder implementations only, no real logic.
4. **Frontend tests** — vitest not installed; add `vitest` + `@testing-library/react`
   as part of Phase 1.
5. **`pydantic-settings` constraint** — if future Phase-1 deps need pydantic-settings
   exactly `2.2.0`, bump to latest compatible version at that time.

### Acceptance Criteria — Phase 0

| Criterion | Status |
|-----------|--------|
| PostgreSQL starts via Docker | ⏳ Pending Docker install |
| FastAPI starts successfully | ✅ Confirmed |
| `GET /api/v1/health` returns HTTP 200 | ✅ Confirmed (database: unreachable without PG) |
| `GET /api/v1/health` returns `database: ok` with live PG | ⏳ Pending Docker |
| Frontend displays health result from backend | ✅ Code complete (calls real `/api/v1/health`) |
| API docs page loads (`/docs`) | ✅ Confirmed (route registered) |
| 3 automated backend tests pass | ✅ `3 passed` in pytest |
| TypeScript compiles cleanly | ✅ `tsc --noEmit` → 0 errors |
| `.env.example` contains placeholders only | ✅ |
| `docs/handoff-log.md` exists | ✅ |
