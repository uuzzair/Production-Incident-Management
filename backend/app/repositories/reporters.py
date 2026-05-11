from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reporter import Reporter
from app.schemas.reporter import ReporterCreate


def normalize_reporter_name(name: str) -> str:
    return " ".join(name.split()).lower()


class ReporterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Reporter]:
        result = await self.session.execute(select(Reporter).order_by(Reporter.name.asc()))
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Reporter | None:
        normalized_name = normalize_reporter_name(name)
        result = await self.session.execute(
            select(Reporter).where(Reporter.normalized_name == normalized_name)
        )
        return result.scalar_one_or_none()

    async def create(self, payload: ReporterCreate) -> Reporter:
        reporter = Reporter(
            name=payload.name,
            normalized_name=normalize_reporter_name(payload.name),
        )
        self.session.add(reporter)
        await self.session.flush()
        await self.session.refresh(reporter)
        return reporter
