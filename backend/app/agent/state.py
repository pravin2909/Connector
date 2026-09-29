import operator
from typing import Annotated, Any, TypedDict


class PendingCall(TypedDict, total=False):
    call_id: str  # id from the LLM
    name: str
    arguments: dict[str, Any]
    parse_error: str | None
    tool_call_db_id: str
    approval_id: str | None
    approval_kind: str | None
    decision: str | None  # approve | reject | None (no approval needed)
    note: str | None


class AgentState(TypedDict, total=False):
    run_id: str
    goal: str
    history: list[dict[str, Any]]  # earlier conversation turns (role/content)
    documents: list[str]  # names of indexed documents, for the system prompt
    available_capabilities: list[str]
    plan: dict[str, Any]
    capabilities: list[str]  # capabilities whose tools are bound to the LLM
    messages: Annotated[list[dict[str, Any]], operator.add]  # tool-loop transcript
    pending: list[PendingCall]
    citations: list[dict[str, Any]]
    step_count: int
    consecutive_errors: int
    replans: int
    rejected: bool
    final_answer: str
