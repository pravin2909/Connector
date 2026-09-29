"""PostgreSQL application state.

Qdrant holds vectors, the filesystem holds user files; everything the app needs to
remember about users, conversations and agent execution lives here.
"""

import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map: ClassVar = {dict[str, Any]: JSONB, list[Any]: JSONB}


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = _created_at()


class Session(Base):
    """A client session (browser/device) belonging to a user."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = _created_at()
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    """Lightweight conversation record: title + preview for the sidebar rail."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    color: Mapped[str] = mapped_column(String(16), default="#E0A03D")
    preview: Mapped[str | None] = mapped_column(String(280))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))
    citations: Mapped[list[Any]] = mapped_column(default=list)
    created_at: Mapped[datetime] = _created_at()

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"))
    goal: Mapped[str] = mapped_column(Text)
    # pending | running | awaiting_approval | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    plan: Mapped[dict[str, Any] | None] = mapped_column()
    model: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)


class AgentStep(Base):
    """High-level, user-safe execution events shown in the Activity panel."""

    __tablename__ = "agent_steps"
    __table_args__ = (UniqueConstraint("agent_run_id", "seq"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    agent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16), default="done")  # running | done | warning | error
    detail: Mapped[dict[str, Any] | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = _uuid_pk()
    agent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    call_id: Mapped[str] = mapped_column(String(128))  # id assigned by the LLM
    server: Mapped[str] = mapped_column(String(32))
    tool_name: Mapped[str] = mapped_column(String(128))
    arguments: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result: Mapped[str | None] = mapped_column(Text)
    # pending | awaiting_approval | rejected | succeeded | failed
    status: Mapped[str] = mapped_column(String(24), default="pending")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = _uuid_pk()
    agent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    tool_call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tool_calls.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16), default="approval")  # approval | handoff
    action: Mapped[str] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|approved|rejected
    note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class FileMetadata(Base):
    """Workspace files the app knows about (uploads, agent-created files)."""

    __tablename__ = "file_metadata"

    id: Mapped[uuid.UUID] = _uuid_pk()
    path: Mapped[str] = mapped_column(String(1024), unique=True)  # relative to FILE_WORKSPACE
    size: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    sha256: Mapped[str] = mapped_column(String(64))
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class Document(Base):
    """A document indexed for RAG. Its chunks/vectors live in Qdrant."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("file_metadata.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(512))
    path: Mapped[str] = mapped_column(String(1024))  # relative to FILE_WORKSPACE
    file_type: Mapped[str] = mapped_column(String(16))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|processing|ready|failed
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
