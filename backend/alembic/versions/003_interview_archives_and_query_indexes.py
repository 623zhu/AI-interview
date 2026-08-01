"""Add durable interview archives and high-frequency query indexes.

Revision ID: 003
Revises: 002
Create Date: 2026-07-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interview_archives",
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("state_data", sa.JSON, nullable=False),
        sa.Column("state_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "archived_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index(
        "idx_sessions_user_created",
        "interview_sessions",
        ["user_id", "created_at"],
    )
    op.create_index(
        "idx_sessions_status_created",
        "interview_sessions",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_reports_user_generated",
        "score_reports",
        ["user_id", "generated_at"],
    )
    op.create_index(
        "idx_resumes_user_created",
        "resumes",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_resumes_user_created", table_name="resumes")
    op.drop_index("idx_reports_user_generated", table_name="score_reports")
    op.drop_index("idx_sessions_status_created", table_name="interview_sessions")
    op.drop_index("idx_sessions_user_created", table_name="interview_sessions")
    op.drop_table("interview_archives")
