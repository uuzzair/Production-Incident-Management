import logging
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transactions import commit_or_rollback
from app.models.incident import Incident, IncidentUpdate
from app.repositories.incidents import IncidentRepository
from app.repositories.reporters import ReporterRepository
from app.schemas.incident import IncidentCreate, IncidentListRead, IncidentUpdateCreate, Pagination

logger = logging.getLogger(__name__)


class IncidentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = IncidentRepository(session)
        self.reporter_repository = ReporterRepository(session)

    async def create_incident(self, payload: IncidentCreate) -> Incident:
        reporter = await self.reporter_repository.get_by_name(payload.created_by)
        if reporter is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reporter must be saved before creating an incident",
            )

        async def operation() -> Incident:
            return await self.repository.create(payload, reporter_id=reporter.id)

        incident = await commit_or_rollback(self.session, operation)
        logger.info("incident_created", extra={"incident_id": incident.id})
        return incident

    async def list_incidents(
        self,
        *,
        status_filter: str | None = None,
        severity_filter: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> IncidentListRead:
        items = await self.repository.list(
            status=status_filter,
            severity=severity_filter,
            created_from=created_from,
            created_to=created_to,
            limit=limit,
            offset=offset,
        )
        total = await self.repository.count(
            status=status_filter,
            severity=severity_filter,
            created_from=created_from,
            created_to=created_to,
        )
        return IncidentListRead(items=items, pagination=Pagination(limit=limit, offset=offset, total=total))

    async def get_incident(self, incident_id: int) -> Incident:
        incident = await self.repository.get(incident_id)
        if incident is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Incident not found",
            )
        return incident

    async def add_update(
        self,
        incident_id: int,
        payload: IncidentUpdateCreate,
    ) -> IncidentUpdate:
        await self.get_incident(incident_id)

        async def operation() -> IncidentUpdate:
            return await self.repository.add_update(incident_id, payload)

        update = await commit_or_rollback(self.session, operation)
        logger.info("incident_update_created", extra={"incident_id": incident_id, "update_id": update.id})
        return update

    async def resolve_incident(self, incident_id: int) -> Incident:
        incident = await self.get_incident(incident_id)
        if incident.status != "resolved":
            async def operation() -> Incident:
                incident.status = "resolved"
                return await self.repository.save(incident)

            incident = await commit_or_rollback(self.session, operation)
            logger.info("incident_resolved", extra={"incident_id": incident.id})
        return incident
