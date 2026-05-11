import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transactions import commit_or_rollback
from app.models.reporter import Reporter
from app.repositories.reporters import ReporterRepository
from app.schemas.reporter import ReporterCreate

logger = logging.getLogger(__name__)


class ReporterService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ReporterRepository(session)

    async def list_reporters(self) -> list[Reporter]:
        return await self.repository.list()

    async def create_reporter(self, payload: ReporterCreate) -> Reporter:
        existing = await self.repository.get_by_name(payload.name)
        if existing:
            return existing

        async def operation() -> Reporter:
            return await self.repository.create(payload)

        reporter = await commit_or_rollback(self.session, operation)
        logger.info("reporter_created", extra={"reporter_id": reporter.id})
        return reporter
