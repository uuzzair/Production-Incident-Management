"""harden reporter identity

Revision ID: 20260512_0005
Revises: 20260511_0004
Create Date: 2026-05-12
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = "20260512_0005"
down_revision: str | None = "20260511_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def normalize_reporter_name(name: str) -> str:
    normalized = " ".join((name or "").split()).lower()
    return normalized or "unknown"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    reporter_columns = {column["name"] for column in inspector.get_columns("reporter")}
    reporter_indexes = {index["name"] for index in inspector.get_indexes("reporter")}

    if "normalized_name" not in reporter_columns:
        op.add_column("reporter", sa.Column("normalized_name", sa.String(length=120), nullable=True))

    reporter_rows = list(bind.execute(text("SELECT id, name FROM reporter ORDER BY id")).mappings())
    normalized_by_id = {
        int(row["id"]): normalize_reporter_name(str(row["name"]))
        for row in reporter_rows
    }

    unknown_ids = [reporter_id for reporter_id, normalized in normalized_by_id.items() if normalized == "unknown"]
    if unknown_ids:
        unknown_id = min(unknown_ids)
    else:
        result = bind.execute(
            text(
                "INSERT INTO reporter (name, normalized_name, created_at) "
                "VALUES (:name, :normalized_name, CURRENT_TIMESTAMP)"
            ),
            {"name": "Unknown", "normalized_name": "unknown"},
        )
        unknown_id = int(result.lastrowid) if bind.dialect.name == "sqlite" else int(
            bind.execute(text("SELECT id FROM reporter WHERE normalized_name = 'unknown'")).scalar_one()
        )
        normalized_by_id[unknown_id] = "unknown"

    canonical_by_normalized: dict[str, int] = {}
    duplicates: list[tuple[int, int]] = []
    for reporter_id in sorted(normalized_by_id):
        normalized = normalized_by_id[reporter_id]
        canonical_id = canonical_by_normalized.setdefault(normalized, reporter_id)
        if canonical_id != reporter_id:
            duplicates.append((reporter_id, canonical_id))

    for reporter_id, normalized in normalized_by_id.items():
        bind.execute(
            text("UPDATE reporter SET normalized_name = :normalized_name WHERE id = :id"),
            {"normalized_name": normalized, "id": reporter_id},
        )

    for duplicate_id, canonical_id in duplicates:
        bind.execute(
            text("UPDATE incident SET reporter_id = :canonical_id WHERE reporter_id = :duplicate_id"),
            {"canonical_id": canonical_id, "duplicate_id": duplicate_id},
        )
        bind.execute(
            text("DELETE FROM reporter WHERE id = :duplicate_id"),
            {"duplicate_id": duplicate_id},
        )

    remaining_reporters = list(bind.execute(text("SELECT id, normalized_name FROM reporter")).mappings())
    reporter_id_by_normalized = {
        str(row["normalized_name"]): int(row["id"])
        for row in remaining_reporters
    }
    created_by_rows = list(
        bind.execute(
            text(
                "SELECT id, created_by FROM incident "
                "WHERE reporter_id IS NULL OR reporter_id NOT IN (SELECT id FROM reporter)"
            )
        ).mappings()
    )
    for row in created_by_rows:
        normalized = normalize_reporter_name(str(row["created_by"]))
        reporter_id = reporter_id_by_normalized.get(normalized, unknown_id)
        bind.execute(
            text("UPDATE incident SET reporter_id = :reporter_id WHERE id = :incident_id"),
            {"reporter_id": reporter_id, "incident_id": int(row["id"])},
        )

    unresolved_count = bind.execute(text("SELECT count(*) FROM incident WHERE reporter_id IS NULL")).scalar_one()
    if unresolved_count:
        raise RuntimeError(
            f"Cannot enforce incident.reporter_id as non-null; {unresolved_count} incidents remain unresolved"
        )

    if "ix_reporter_normalized_name" not in reporter_indexes:
        op.create_index(op.f("ix_reporter_normalized_name"), "reporter", ["normalized_name"], unique=True)

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("reporter", recreate="always") as batch_op:
            batch_op.alter_column("normalized_name", existing_type=sa.String(length=120), nullable=False)

        with op.batch_alter_table("incident", recreate="always") as batch_op:
            batch_op.alter_column("reporter_id", existing_type=sa.Integer(), nullable=False)
    else:
        op.alter_column("reporter", "normalized_name", existing_type=sa.String(length=120), nullable=False)
        op.alter_column("incident", "reporter_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("incident", recreate="always") as batch_op:
            batch_op.alter_column("reporter_id", existing_type=sa.Integer(), nullable=True)
        with op.batch_alter_table("reporter", recreate="always") as batch_op:
            batch_op.drop_index(op.f("ix_reporter_normalized_name"))
            batch_op.drop_column("normalized_name")
    else:
        op.alter_column("incident", "reporter_id", existing_type=sa.Integer(), nullable=True)
        op.drop_index(op.f("ix_reporter_normalized_name"), table_name="reporter")
        op.drop_column("reporter", "normalized_name")
