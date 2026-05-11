# FastAPI Incidents

Incident reporting application split into separate production-oriented folders:

- `backend/`: FastAPI API with async SQLAlchemy, Alembic migrations, repositories, services, and structured JSON logging.
- `frontend/`: Vue 3 + Vite incident reporting console.

## Backend

From the project root:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8001
```

Or from inside `backend/`:

```powershell
cd C:\OfficeWork\Python-Scripts\fastapi_incidents\backend
..\venv\Scripts\python.exe -m pip install -r requirements.txt
..\venv\Scripts\python.exe -m alembic upgrade head
..\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

Local write APIs require an API key. The default local key is `local-dev-token`; send it as `Authorization: Bearer local-dev-token` or `X-API-Key: local-dev-token`.

## Frontend

```powershell
cd C:\OfficeWork\Python-Scripts\fastapi_incidents\frontend
npm install
npm run dev
```

The frontend reads `VITE_API_URL` from `frontend/.env.local`. For local development, use:

```powershell
VITE_API_URL=http://127.0.0.1:8000/api/v1
```

The frontend never reads or embeds API tokens. Local write testing should use the backend API directly with `Authorization: Bearer local-dev-token` until browser user authentication is added.

## Docker

```powershell
docker compose up --build
```

This starts PostgreSQL, runs backend migrations, serves the API on `http://127.0.0.1:8001`, and serves the frontend on `http://127.0.0.1:8080`.
The containerized frontend is built without any browser-embedded API token; write actions require a proper browser auth rollout.

## Notes

The previous root-level FastAPI modules were removed from active use. Some old local artifacts such as SQLite files, logs, `configs/`, `routes/`, and `__pycache__/` may remain if Windows has them locked or permission-protected; the production app entrypoint is now `backend/app/main.py`.
