"""Create request logs and trace events.

Revision ID: 20261019_0001
Revises:
Create Date: 2026-10-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "request_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("complexity", sa.String(length=32), nullable=True),
        sa.Column("selected_model", sa.String(length=128), nullable=True),
        sa.Column("final_model", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), nullable=True),
        sa.Column("cache_key", sa.String(length=256), nullable=True),
        sa.Column("cache_lookup_latency_ms", sa.Float(), nullable=True),
        sa.Column("context_before_tokens", sa.Integer(), nullable=True),
        sa.Column("context_after_tokens", sa.Integer(), nullable=True),
        sa.Column("context_reduction_percent", sa.Float(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("quality_status", sa.String(length=32), nullable=True),
        sa.Column("escalated", sa.Boolean(), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_request_logs_timestamp", "request_logs", ["timestamp"])
    op.create_table(
        "request_trace_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["request_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trace_request_timestamp",
        "request_trace_events",
        ["request_id", "timestamp", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_trace_request_timestamp", table_name="request_trace_events")
    op.drop_table("request_trace_events")
    op.drop_index("ix_request_logs_timestamp", table_name="request_logs")
    op.drop_table("request_logs")
