import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExecutionArtifact(Base):
    __tablename__ = "execution_artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("executions.id"), index=True)
    # one of: trace|log|screenshot|dump|network|tool_calls
    artifact_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(256))
    blob_key: Mapped[str] = mapped_column(String(512))
    size: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(128))


class ExecutionClaim(Base):
    __tablename__ = "execution_claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("executions.id"), index=True)
    claim_text: Mapped[str] = mapped_column(Text)
    # the agent that filed the claim (the run's tester); a different agent must
    # verify it. Null = unattributed (can't enforce doer != checker).
    claimant_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ClaimVerification(Base):
    __tablename__ = "claim_verifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("execution_claims.id"), index=True)
    auditor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    verdict: Mapped[str] = mapped_column(String(16))  # confirmed|refuted|inconclusive
    reasoning: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExecutionReasoning(Base):
    __tablename__ = "execution_reasoning"
    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("executions.id"), index=True)
    reasoning: Mapped[dict | None] = mapped_column(JSONB)
    agent_model: Mapped[str | None] = mapped_column(String(128))
    agent_session_id: Mapped[str | None] = mapped_column(String(128))
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    # cleaned root-cause text (embeddings.embed_text_for) — the same text we embed,
    # stored so keyword/full-text retrieval indexes prose, not the raw JSON dump.
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditReport(Base):
    __tablename__ = "audit_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32))  # case_version|suite|plan
    entity_id: Mapped[int] = mapped_column(Integer)
    auditor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    findings: Mapped[dict | None] = mapped_column(JSONB)
    quality_score: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
