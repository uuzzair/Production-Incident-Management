"""add incident constraints and reporter foreign key

Revision ID: 20260511_0004
Revises: 20260507_0003
Create Date: 2026-05-11
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260511_0004"
down_revision: str | None = "20260507_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("incident")}
    indexes = {index["name"] for index in inspector.get_indexes("incident")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("incident")}
    check_constraints = {constraint["name"] for constraint in inspector.get_check_constraints("incident")}

    if "reporter_id" not in columns:
        op.add_column("incident", sa.Column("reporter_id", sa.Integer(), nullable=True))

    if "ix_incident_reporter_id" not in indexes:
        op.create_index(op.f("ix_incident_reporter_id"), "incident", ["reporter_id"], unique=False)

    op.execute(
        """
        UPDATE incident
        SET reporter_id = (
            SELECT reporter.id
            FROM reporter
            WHERE lower(reporter.name) = lower(incident.created_by)
            LIMIT 1
        )
        WHERE reporter_id IS NULL
        """
    )

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("incident", recreate="always") as batch_op:
            if "fk_incident_reporter_id_reporter" not in foreign_keys:
                batch_op.create_foreign_key(
                    "fk_incident_reporter_id_reporter",
                    "reporter",
                    ["reporter_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
            if "ck_incident_severity" not in check_constraints:
                batch_op.create_check_constraint(
                    "ck_incident_severity",
                    "severity IN ('low', 'medium', 'high', 'critical')",
                )
            if "ck_incident_status" not in check_constraints:
                batch_op.create_check_constraint(
                    "ck_incident_status",
                    "status IN ('open', 'resolved')",
                )
    else:
        if "fk_incident_reporter_id_reporter" not in foreign_keys:
            op.create_foreign_key(
                "fk_incident_reporter_id_reporter",
                "incident",
                "reporter",
                ["reporter_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        if "ck_incident_severity" not in check_constraints:
            op.create_check_constraint(
                "ck_incident_severity",
                "incident",
                "severity IN ('low', 'medium', 'high', 'critical')",
            )
        if "ck_incident_status" not in check_constraints:
            op.create_check_constraint(
                "ck_incident_status",
                "incident",
                "status IN ('open', 'resolved')",
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("incident", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_incident_status", type_="check")
            batch_op.drop_constraint("ck_incident_severity", type_="check")
            batch_op.drop_constraint("fk_incident_reporter_id_reporter", type_="foreignkey")
            batch_op.drop_index(op.f("ix_incident_reporter_id"))
            batch_op.drop_column("reporter_id")
    else:
        op.drop_constraint("ck_incident_status", "incident", type_="check")
        op.drop_constraint("ck_incident_severity", "incident", type_="check")
        op.drop_constraint("fk_incident_reporter_id_reporter", "incident", type_="foreignkey")
        op.drop_index(op.f("ix_incident_reporter_id"), table_name="incident")
        op.drop_column("incident", "reporter_id")
