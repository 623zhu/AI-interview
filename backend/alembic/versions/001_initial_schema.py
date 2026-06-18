"""Initial database schema - all 8 tables.

Revision ID: 001
Revises: None
Create Date: 2026-06-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("avatar_url", sa.String(500), default=None),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("is_admin", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), onupdate=sa.func.current_timestamp()),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_username", "users", ["username"])

    # resumes
    op.create_table(
        "resumes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False),
        sa.Column("raw_text", sa.Text(length=16777215), default=None),
        sa.Column("parsed_data", sa.JSON, default=None),
        sa.Column("parse_status", sa.String(20), default="pending"),
        sa.Column("parse_error", sa.String(500), default=None),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), onupdate=sa.func.current_timestamp()),
    )
    op.create_index("idx_resumes_user", "resumes", ["user_id"])
    op.create_index("idx_resumes_status", "resumes", ["parse_status"])

    # job_positions
    op.create_table(
        "job_positions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("level", sa.String(20), nullable=False, server_default="mid"),
        sa.Column("description", sa.Text, default=None),
        sa.Column("requirements", sa.JSON, nullable=False),
        sa.Column("skill_tree", sa.JSON, default=None),
        sa.Column("salary_range", sa.String(50), default=None),
        sa.Column("company_type", sa.String(50), server_default="互联网"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), onupdate=sa.func.current_timestamp()),
    )
    op.create_index("idx_jobs_category", "job_positions", ["category"])
    op.create_index("idx_jobs_level", "job_positions", ["level"])
    op.create_index("idx_jobs_active", "job_positions", ["is_active"])

    # resume_job_matches
    op.create_table(
        "resume_job_matches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("resume_id", sa.String(36), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("job_positions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_score", sa.Integer, nullable=False),
        sa.Column("score_breakdown", sa.JSON, default=None),
        sa.Column("matched_skills", sa.JSON, default=None),
        sa.Column("missing_skills", sa.JSON, default=None),
        sa.Column("match_reason", sa.Text, default=None),
        sa.Column("advice", sa.Text, default=None),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )
    op.create_unique_constraint("uk_resume_job", "resume_job_matches", ["resume_id", "job_id"])
    op.create_index("idx_matches_resume", "resume_job_matches", ["resume_id"])
    op.create_index("idx_matches_job", "resume_job_matches", ["job_id"])
    op.create_index("idx_matches_score", "resume_job_matches", ["match_score"])

    # questions
    op.create_table(
        "questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("difficulty", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("job_category", sa.String(50), default=None),
        sa.Column("job_level", sa.String(20), default=None),
        sa.Column("skill_nodes", sa.JSON, default=None),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("expected_points", sa.Text, default=None),
        sa.Column("reference_answer", sa.Text, default=None),
        sa.Column("evaluation_criteria", sa.JSON, default=None),
        sa.Column("chroma_doc_id", sa.String(100), default=None),
        sa.Column("source", sa.String(20), server_default="seed"),
        sa.Column("usage_count", sa.Integer, default=0),
        sa.Column("avg_score", sa.Float(5, 2), default=None),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), onupdate=sa.func.current_timestamp()),
    )
    op.create_index("idx_q_category", "questions", ["category"])
    op.create_index("idx_q_difficulty", "questions", ["difficulty"])
    op.create_index("idx_q_job_category", "questions", ["job_category"])
    op.create_index("idx_q_chroma", "questions", ["chroma_doc_id"])

    # interview_sessions
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_id", sa.String(36), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("job_positions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="created"),
        sa.Column("config", sa.JSON, default=None),
        sa.Column("questions", sa.JSON, default=None),
        sa.Column("total_questions", sa.Integer, default=0),
        sa.Column("current_question", sa.Integer, default=0),
        sa.Column("started_at", sa.DateTime, default=None),
        sa.Column("completed_at", sa.DateTime, default=None),
        sa.Column("duration_seconds", sa.Integer, default=None),
        sa.Column("report_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("report_error", sa.String(500), default=None),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp(), onupdate=sa.func.current_timestamp()),
    )
    op.create_index("idx_sessions_user", "interview_sessions", ["user_id"])
    op.create_index("idx_sessions_status", "interview_sessions", ["status"])

    # interview_messages
    op.create_table(
        "interview_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("message_type", sa.String(30), default=None),
        sa.Column("question_id", sa.String(36), default=None),
        sa.Column("scores", sa.JSON, default=None),
        sa.Column("extra_data", sa.JSON, default=None),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )
    op.create_index("idx_messages_session", "interview_messages", ["session_id"])
    op.create_index("idx_messages_created", "interview_messages", ["created_at"])

    # interview_question_links
    op.create_table(
        "interview_question_links",
        sa.Column("interview_id", sa.String(36), sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("question_id", sa.String(36), sa.ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True),
    )

    # score_reports
    op.create_table(
        "score_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("overall_score", sa.Integer, nullable=False),
        sa.Column("dimension_scores", sa.JSON, nullable=False),
        sa.Column("question_evaluations", sa.JSON, nullable=False),
        sa.Column("strengths", sa.JSON, default=None),
        sa.Column("weaknesses", sa.JSON, default=None),
        sa.Column("improvements", sa.JSON, default=None),
        sa.Column("full_report", sa.Text(length=16777215), nullable=False),
        sa.Column("full_data", sa.JSON, default=None),
        sa.Column("generated_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )
    op.create_index("idx_reports_user", "score_reports", ["user_id"])
    op.create_index("idx_reports_session", "score_reports", ["session_id"])


def downgrade() -> None:
    op.drop_table("score_reports")
    op.drop_table("interview_messages")
    op.drop_table("interview_question_links")
    op.drop_table("interview_sessions")
    op.drop_table("questions")
    op.drop_table("resume_job_matches")
    op.drop_table("job_positions")
    op.drop_table("resumes")
    op.drop_table("users")
