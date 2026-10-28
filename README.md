# BankTech Analytics

An intelligent banking analytics and regulatory-compliance platform.

> **Status**: Phase 0 — scaffold & health check only.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript, Vite 8, Tailwind CSS 4 |
| Backend | FastAPI, Python 3.14, SQLAlchemy 2 (async), asyncpg |
| Database | PostgreSQL 16 |
| Orchestration | Docker Compose (dev) |

---

## Prerequisites

| Tool | Minimum version | Install |
|------|----------------|---------|
| Node.js | 18 | https://nodejs.org |
| Python | 3.11 | https://python.org |
| Docker Desktop | latest | https://docs.docker.com/get-docker/ |

---

## Quick Start (local dev — three terminals)

### Terminal 1 — PostgreSQL via Docker

```powershell
# From repo root
docker compose up postgres
```

### Terminal 2 — FastAPI backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env   # then edit .env with real DB creds
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Terminal 3 — React frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173

---

## Environment Variables

Copy `.env.example` → `.env` and fill in every `<placeholder>` value:

```powershell
Copy-Item .env.example .env
```

**Never commit `.env` to version control.**

---

## Running Tests

### Backend unit tests

```powershell
cd backend
.venv\Scripts\activate
pytest tests/ -v
```

---

## Project Structure

```
BankTech-Analytics/
├── frontend/                 # React + TypeScript + Tailwind (Vite)
│   └── src/
│       ├── App.tsx           # Health-check page (Phase 0)
│       └── main.tsx
├── backend/
│   └── app/
│       ├── core/
│       │   ├── config.py     # Pydantic-settings env config
│       │   └── database.py   # Async SQLAlchemy engine
│       ├── api/
│       │   └── health.py     # GET /api/v1/health
│       ├── analytics/        # Phase 1 stub
│       ├── auth/             # Phase 1 stub
│       ├── rag/              # Phase 2 stub
│       └── main.py           # FastAPI app
│   ├── tests/
│   │   └── test_health.py
│   ├── requirements.txt
│   └── pytest.ini
├── data/
│   ├── knowledge_base/       # Regulatory docs (Phase 2)
│   └── sample/               # Synthetic datasets (Phase 1)
├── docs/
│   ├── architecture-blueprint.pdf
│   └── handoff-log.md
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Phases

| Phase | Scope | Status |
|-------|-------|--------|
| **0** | Scaffold, health endpoint, Vite proxy, health UI, tests | ✅ Complete |
| 1 | Auth (JWT), transaction analytics, dashboard | 🔜 Pending |
| 2 | RAG compliance assistant (LangChain + ChromaDB) | 🔜 Pending |
