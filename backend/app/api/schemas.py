import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ConversationOut(ORM):
    id: uuid.UUID
    title: str
    color: str
    preview: str | None
    created_at: datetime
    updated_at: datetime


class ConversationCreate(BaseModel):
    title: str | None = None
    color: str | None = None


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    color: str | None = None


class MessageOut(ORM):
    id: uuid.UUID
    role: str
    content: str
    agent_run_id: uuid.UUID | None
    citations: list[Any]
    created_at: datetime


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class StepOut(ORM):
    seq: int
    kind: str
    label: str
    status: str
    detail: dict[str, Any] | None
    created_at: datetime


class ToolCallOut(ORM):
    id: uuid.UUID
    server: str
    tool_name: str
    arguments: dict[str, Any]
    result: str | None
    status: str
    latency_ms: int | None
    created_at: datetime


class RunOut(ORM):
    id: uuid.UUID
    conversation_id: uuid.UUID
    goal: str
    status: str
    plan: dict[str, Any] | None
    model: str | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None


class RunDetail(RunOut):
    steps: list[StepOut] = []
    tool_calls: list[ToolCallOut] = []
    approvals: list[dict[str, Any]] = []


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
    runs: list[RunDetail]


class SendResult(BaseModel):
    message: MessageOut
    run: RunOut


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = None


class DocumentOut(ORM):
    id: uuid.UUID
    filename: str
    path: str
    file_type: str
    size: int
    status: str
    chunk_count: int
    page_count: int | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class IndexPathIn(BaseModel):
    path: str


class SearchIn(BaseModel):
    query: str
    top_k: int | None = None
    documents: list[str] | None = None
