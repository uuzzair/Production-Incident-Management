from datetime import date, datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import require_roles
from app.db.session import get_db_session
from app.schemas.incident import (
    IncidentCreate,
    IncidentDetailRead,
    IncidentListRead,
    IncidentRead,
    IncidentStatus,
    IncidentUpdateCreate,
    IncidentUpdateRead,
    Severity,
)
from app.services.incidents import IncidentService

router = APIRouter(prefix="/incidents", tags=["Incidents"])


def get_incident_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IncidentService:
    return IncidentService(session)


@router.post("/", response_model=IncidentRead, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreate,
    service: Annotated[IncidentService, Depends(get_incident_service)],
    _principal: Annotated[object, Depends(require_roles("admin", "responder", "reporter"))],
):
    return await service.create_incident(payload)


@router.get("/", response_model=IncidentListRead)
async def list_incidents(
    service: Annotated[IncidentService, Depends(get_incident_service)],
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    severity_filter: Annotated[Severity | None, Query(alias="severity")] = None,
    created_from: Annotated[date | None, Query(description="Start date, inclusive")] = None,
    created_to: Annotated[date | None, Query(description="End date, inclusive")] = None,
    limit: Annotated[int, Query(ge=1, le=get_settings().max_page_limit)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await service.list_incidents(
        status_filter=status_filter,
        severity_filter=severity_filter,
        created_from=start_of_day(created_from),
        created_to=end_of_day(created_to),
        limit=limit,
        offset=offset,
    )


def start_of_day(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def end_of_day(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


@router.get("/{incident_id}", response_model=IncidentDetailRead)
async def get_incident(
    incident_id: int,
    service: Annotated[IncidentService, Depends(get_incident_service)],
):
    return await service.get_incident(incident_id)


@router.post(
    "/{incident_id}/updates",
    response_model=IncidentUpdateRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_incident_update(
    incident_id: int,
    payload: IncidentUpdateCreate,
    service: Annotated[IncidentService, Depends(get_incident_service)],
    _principal: Annotated[object, Depends(require_roles("admin", "responder"))],
):
    return await service.add_update(incident_id, payload)


@router.patch("/{incident_id}/resolve", response_model=IncidentRead)
async def resolve_incident(
    incident_id: int,
    service: Annotated[IncidentService, Depends(get_incident_service)],
    _principal: Annotated[object, Depends(require_roles("admin", "responder"))],
):
    return await service.resolve_incident(incident_id)
