import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    item_counts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    themes: Mapped[list["Theme"]] = relationship(back_populates="pipeline_run")
    segments: Mapped[list["Segment"]] = relationship(back_populates="pipeline_run")
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="pipeline_run")
    answers: Mapped[list["Answer"]] = relationship(back_populates="pipeline_run")
    unmet_needs: Mapped[list["UnmetNeed"]] = relationship(back_populates="pipeline_run")


class RawDocument(Base):
    __tablename__ = "raw_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(64), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    feedback_items: Mapped[list["FeedbackItem"]] = relationship(back_populates="raw_document")


class FeedbackItem(Base):
    __tablename__ = "feedback_items"
    __table_args__ = (UniqueConstraint("source", "content_hash", name="uq_feedback_source_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    raw_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_documents.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    raw_document: Mapped[RawDocument | None] = relationship(back_populates="feedback_items")
    themes: Mapped[list["Theme"]] = relationship(
        secondary="feedback_themes", back_populates="feedback_items"
    )
    analysis: Mapped["Analysis | None"] = relationship(
        back_populates="feedback_item", uselist=False
    )


class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    mention_volume: Mapped[int] = mapped_column(Integer, default=0)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    representative_quote_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True
    )

    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="themes")
    feedback_items: Mapped[list[FeedbackItem]] = relationship(
        secondary="feedback_themes", back_populates="themes"
    )


class FeedbackTheme(Base):
    __tablename__ = "feedback_themes"

    feedback_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feedback_items.id"), primary_key=True
    )
    theme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("themes.id"), primary_key=True
    )


class ClusterAssignment(Base):
    __tablename__ = "cluster_assignments"
    __table_args__ = (
        UniqueConstraint(
            "feedback_item_id",
            "pipeline_run_id",
            name="uq_cluster_assignment_item_run",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feedback_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feedback_items.id"), index=True
    )
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True
    )
    cluster_id: Mapped[int] = mapped_column(Integer)

    feedback_item: Mapped[FeedbackItem] = relationship()
    pipeline_run: Mapped[PipelineRun] = relationship()


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(128))
    top_frustration: Mapped[str | None] = mapped_column(Text, nullable=True)
    top_unmet_need: Mapped[str | None] = mapped_column(Text, nullable=True)
    top_behavior: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True
    )

    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="segments")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feedback_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feedback_items.id"), unique=True, index=True
    )
    sentiment_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    behavior_signals: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    segment_hint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True
    )

    feedback_item: Mapped[FeedbackItem] = relationship(back_populates="analysis")
    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="analyses")


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("question_id", "pipeline_run_id", name="uq_answer_question_run"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[str] = mapped_column(String(8), index=True)
    answer_text: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True
    )

    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="answers")


class UnmetNeed(Base):
    __tablename__ = "unmet_needs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    description: Mapped[str] = mapped_column(Text)
    frequency: Mapped[int] = mapped_column(Integer, default=0)
    urgency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_attribution: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True
    )

    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="unmet_needs")
