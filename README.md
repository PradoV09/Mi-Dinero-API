# Mi Dinero

App personal de finanzas (React + Vite + TS / FastAPI / PostgreSQL). Estado: **esqueleto con /health** (PostgreSQL, cuentas y auth aun no).

## Backend
    cd backend
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    pytest
    uvicorn app.main:app --reload --port 8000   # http://localhost:8000/health

## Frontend
    cd frontend
    npm install
    npm run dev   # http://localhost:5173

## Siguiente paso
PostgreSQL + SQLAlchemy async + Alembic, luego Fase 2 (cuentas).
