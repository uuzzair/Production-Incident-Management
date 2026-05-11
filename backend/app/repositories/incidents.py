from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.incident import Incident, IncidentUpdate
from app.schemas.incident import IncidentCreate, IncidentUpdateCreate


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: IncidentCreate, reporter_id: int) -> Incident:
        incident = Incident(
            title=payload.title,
            reporter_id=reporter_id,
            created_by=payload.created_by,
            severity=payload.severity,
            description=payload.description,
        )
        self.session.add(incident)
        await self.session.flush()
        await self.session.refresh(incident)
        return incident

    async def list(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Incident]:
        statement = self._filtered_statement(
            status=status,
            severity=severity,
            created_from=created_from,
            created_to=created_to,
        ).order_by(Incident.created_at.desc(), Incident.id.desc())
        statement = statement.limit(limit).offset(offset)

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> int:
        statement = self._filtered_statement(
            status=status,
            severity=severity,
            created_from=created_from,
            created_to=created_to,
        )
        count_statement = select(func.count()).select_from(statement.subquery())
        result = await self.session.execute(count_statement)
        return int(result.scalar_one())

    def _filtered_statement(
        self,
        *,
        status: str | None,
        severity: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> Select[tuple[Incident]]:
        statement: Select[tuple[Incident]] = select(Incident)

        if status:
            statement = statement.where(Incident.status == status)

        if severity:
            statement = statement.where(Incident.severity == severity)

        if created_from:
            statement = statement.where(Incident.created_at >= created_from)

        if created_to:
            statement = statement.where(Incident.created_at <= created_to)

        return statement

    async def get(self, incident_id: int) -> Incident | None:
        statement = (
            select(Incident)
            .where(Incident.id == incident_id)
            .options(selectinload(Incident.updates))
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def add_update(self, incident_id: int, payload: IncidentUpdateCreate) -> IncidentUpdate:
        update = IncidentUpdate(incident_id=incident_id, message=payload.message)
        self.session.add(update)
        await self.session.flush()
        await self.session.refresh(update)
        return update

    async def save(self, incident: Incident) -> Incident:
        self.session.add(incident)
        await self.session.flush()
        await self.session.refresh(incident)
        return incident
