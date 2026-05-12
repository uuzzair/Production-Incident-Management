"""add session csrf

Revision ID: 20260513_0007
Revises: 20260512_0006
Create Date: 2026-05-13 00:07:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260513_0007"
down_revision: str | None = "20260512_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_sessions", sa.Column("csrf_token_hash", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("user_sessions", "csrf_token_hash")
