from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.reporters import router as reporters_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.db.session import engine

settings = get_settings()
configure_logging(settings)
BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI_PATH = BACKEND_DIR / "alembic.ini"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
register_exception_handlers(app)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_cookie_secret,
    session_cookie=settings.oidc_state_cookie_name,
    max_age=600,
    same_site="lax",
    https_only=settings.secure_cookies,
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_origin_regex=settings.cors_allowed_origin_regex,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready", tags=["Health"])
async def readiness_check():
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
        current_revision = await connection.run_sync(get_current_revision)

    expected_revision = get_expected_revision()
    is_ready = current_revision == expected_revision
    payload = {
        "status": "ready" if is_ready else "not_ready",
        "environment": settings.environment,
        "database_revision": current_revision,
        "expected_revision": expected_revision,
    }
    if not is_ready:
        raise HTTPException(status_code=503, detail=payload)
    return payload


app.include_router(incidents_router, prefix="/api/v1")
app.include_router(reporters_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")


@lru_cache
def get_expected_revision() -> str:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()


def get_current_revision(connection) -> str | None:
    context = MigrationContext.configure(connection)
    return context.get_current_revision()
