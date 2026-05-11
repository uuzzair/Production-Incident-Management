# Incident Reporting Frontend

Vue 3 + Vite frontend for the FastAPI incident reporting backend.

## Run locally

```powershell
cd C:\OfficeWork\Python-Scripts\fastapi_incidents\backend
..\venv\Scripts\python.exe -m alembic upgrade head
..\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

```powershell
cd C:\OfficeWork\Python-Scripts\fastapi_incidents\frontend
npm install
npm run dev
```

The frontend defaults to `http://127.0.0.1:8001/api/v1` through `.env.local`. Override it with:

```powershell
$env:VITE_API_URL="http://127.0.0.1:8001/api/v1"
npm run dev
```

The frontend does not read API tokens. Use the backend API directly for local write testing until browser user authentication is added.
