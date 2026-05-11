from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_roles
from app.db.session import get_db_session
from app.schemas.reporter import ReporterCreate, ReporterRead
from app.services.reporters import ReporterService

router = APIRouter(prefix="/reporters", tags=["Reporters"])


def get_reporter_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReporterService:
    return ReporterService(session)


@router.get("/", response_model=list[ReporterRead])
async def list_reporters(
    service: Annotated[ReporterService, Depends(get_reporter_service)],
):
    return await service.list_reporters()


@router.post("/", response_model=ReporterRead, status_code=status.HTTP_201_CREATED)
async def create_reporter(
    payload: ReporterCreate,
    service: Annotated[ReporterService, Depends(get_reporter_service)],
    _principal: Annotated[object, Depends(require_roles("admin", "responder", "reporter"))],
):
    return await service.create_reporter(payload)
