"""Add report generation status to interview sessions.

Revision ID: 002
Revises: 001
Create Date: 2026-06-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions",
        sa.Column("report_status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "interview_sessions",
        sa.Column("report_error", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_sessions", "report_error")
    op.drop_column("interview_sessions", "report_status")
