"""add incident created_by

Revision ID: 20260507_0002
Revises: 20260507_0001
Create Date: 2026-05-07
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260507_0002"
down_revision: str | None = "20260507_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("incident")}
    indexes = {index["name"] for index in inspector.get_indexes("incident")}

    if "created_by" not in columns:
        op.add_column(
            "incident",
            sa.Column("created_by", sa.String(length=120), nullable=False, server_default="Unknown"),
        )

    if "ix_incident_created_by" not in indexes:
        op.create_index(op.f("ix_incident_created_by"), "incident", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_incident_created_by"), table_name="incident")
    op.drop_column("incident", "created_by")
