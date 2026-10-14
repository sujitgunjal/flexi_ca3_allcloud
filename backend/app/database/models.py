"""ORM models for persisted gateway evaluation data."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class RequestLog(Base):
    """One gateway request and its optional evaluation measurements."""

    __tablename__ = "request_logs"
    __table_args__ = (Index("ix_request_logs_timestamp", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    complexity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    selected_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    final_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    cache_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cache_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    cache_lookup_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_before_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_after_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_reduction_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    escalated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fallback_used: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Nullable keeps pre-upgrade rows distinguishable from explicit outcomes.
    completed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class RequestTraceEvent(Base):
    """A timestamped, provider-independent event in a request execution trace."""

    __tablename__ = "request_trace_events"
    __table_args__ = (Index("ix_trace_request_timestamp", "request_id", "timestamp", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("request_logs.id", ondelete="CASCADE"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
