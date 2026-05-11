"""create reporters

Revision ID: 20260507_0003
Revises: 20260507_0002
Create Date: 2026-05-07
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260507_0003"
down_revision: str | None = "20260507_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "reporter",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_reporter_id"), "reporter", ["id"], unique=False)
    op.create_index(op.f("ix_reporter_name"), "reporter", ["name"], unique=True)
    if bind.dialect.name == "sqlite":
        op.execute(
            """
            INSERT OR IGNORE INTO reporter (name, created_at)
            SELECT DISTINCT created_by, CURRENT_TIMESTAMP
            FROM incident
            WHERE created_by IS NOT NULL AND trim(created_by) != ''
            """
        )
    elif bind.dialect.name == "postgresql":
        op.execute(
            """
            INSERT INTO reporter (name, created_at)
            SELECT DISTINCT created_by, CURRENT_TIMESTAMP
            FROM incident
            WHERE created_by IS NOT NULL AND trim(created_by) != ''
            ON CONFLICT (name) DO NOTHING
            """
        )
    else:
        op.execute(
            """
            INSERT INTO reporter (name, created_at)
            SELECT DISTINCT created_by, CURRENT_TIMESTAMP
            FROM incident
            WHERE created_by IS NOT NULL AND trim(created_by) != ''
            """
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_reporter_name"), table_name="reporter")
    op.drop_index(op.f("ix_reporter_id"), table_name="reporter")
    op.drop_table("reporter")
