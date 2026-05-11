"""create incident tables

Revision ID: 20260507_0001
Revises:
Create Date: 2026-05-07
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260507_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incident",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_incident_id"), "incident", ["id"], unique=False)
    op.create_index(op.f("ix_incident_severity"), "incident", ["severity"], unique=False)
    op.create_index(op.f("ix_incident_status"), "incident", ["status"], unique=False)

    op.create_table(
        "incident_update",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incident.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_incident_update_id"), "incident_update", ["id"], unique=False)
    op.create_index(
        op.f("ix_incident_update_incident_id"),
        "incident_update",
        ["incident_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_incident_update_incident_id"), table_name="incident_update")
    op.drop_index(op.f("ix_incident_update_id"), table_name="incident_update")
    op.drop_table("incident_update")
    op.drop_index(op.f("ix_incident_status"), table_name="incident")
    op.drop_index(op.f("ix_incident_severity"), table_name="incident")
    op.drop_index(op.f("ix_incident_id"), table_name="incident")
    op.drop_table("incident")
