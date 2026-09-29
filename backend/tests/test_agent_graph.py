"""End-to-end agent loop with a scripted LLM and fake tools (needs the Postgres from docker compose)."""

import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from app.agent.events import Emitter, EventBus
from app.agent.graph import build_graph
from app.agent.nodes import AgentDeps
from app.agent.policy import PolicyEngine
from app.agent.runner import AgentRunner
from app.agent.tools import ToolOutput, ToolSpec
from app.config import get_settings
from app.db.models import AgentRun, Approval, Conversation, Message, ToolCall
from app.db.session import SessionLocal, ensure_local_user
from app.llm.base import LLMResponse, ToolCallRequest


class ScriptedLLM:
    model = "scripted"

    def __init__(self, plan, responses):
        self.plan = plan
        self.responses = list(responses)
        self.seen: list[list[dict]] = []

    async def complete_json(self, messages, schema, name="result"):
        return self.plan

    async def chat(self, messages, tools=None, temperature=None):
        self.seen.append(messages)
        return self.responses.pop(0)

    async def list_models(self):
        return [self.model]


class FakeRegistry:
    def __init__(self):
        self.calls = []
        self._specs = {
            "email__find_contact": ToolSpec("email__find_contact", "email", "find_contact", "", {}, read_only=True),
            "email__send_email": ToolSpec("email__send_email", "email", "send_email", "", {}, destructive=True),
        }

    def specs(self):
        return self._specs

    def available_capabilities(self):
        return ["documents", "email"]

    def schemas_for(self, caps):
        return [s.openai_schema() for s in self._specs.values() if s.capability in caps]

    async def call(self, name, args):
        self.calls.append((name, args))
        if name == "email__find_contact":
            return ToolOutput('[{"name": "Rahul", "email": "rahul@example.com"}]')
        return ToolOutput('{"status": "sent"}')


def tc(name, args):
    import json

    return ToolCallRequest(id=f"call_{uuid.uuid4().hex[:6]}", name=name, arguments=args, raw_arguments=json.dumps(args))


async def _setup(llm, registry):
    settings = get_settings()
    bus = EventBus()
    emitter = Emitter(bus)
    deps = AgentDeps(llm, registry, PolicyEngine(registry), emitter, settings)
    graph = build_graph(deps, InMemorySaver())
    runner = AgentRunner(graph, bus, emitter, "scripted", 10)
    user = await ensure_local_user()
    async with SessionLocal() as db:
        convo = Conversation(user_id=user.id, title="test")
        db.add(convo)
        await db.commit()
        return runner, bus, convo.id


async def _drain(bus, run_id):
    return [e async for e in bus.subscribe(run_id)]


@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_send_email_pauses_for_approval(decision):
    email = {"to": "rahul@example.com", "subject": "Report", "body": "Hi Rahul"}
    llm = ScriptedLLM(
        {"summary": "email rahul", "needs_tools": True, "capabilities": ["email"], "steps": ["find", "send"]},
        [
            LLMResponse("", [tc("email__find_contact", {"name": "Rahul"})]),
            LLMResponse("", [tc("email__send_email", email)]),
            LLMResponse("Sent the report to Rahul." if decision == "approve" else "Not sent: you rejected it."),
        ],
    )
    registry = FakeRegistry()
    runner, bus, convo_id = await _setup(llm, registry)

    _, run = await runner.start(convo_id, "Email Rahul the report")
    events = await _drain(bus, str(run.id))
    assert events[-1] == {**events[-1], "type": "done", "status": "awaiting_approval"}
    approval_evt = next(e for e in events if e["type"] == "approval_required")
    assert [a["action"] for a in approval_evt["approvals"]] == ["email__send_email"]
    # The consequential tool must not have run yet.
    assert [c[0] for c in registry.calls] == ["email__find_contact"]

    await runner.decide(uuid.UUID(approval_evt["approvals"][0]["id"]), decision, None)
    events = await _drain(bus, str(run.id))
    assert events[-1]["status"] == "completed"

    sent = [c for c in registry.calls if c[0] == "email__send_email"]
    assert sent == ([("email__send_email", email)] if decision == "approve" else [])

    async with SessionLocal() as db:
        r = await db.get(AgentRun, run.id)
        assert r.status == "completed"
        calls = (await db.scalars(select(ToolCall).where(ToolCall.agent_run_id == run.id))).all()
        assert {c.tool_name: c.status for c in calls}["email__send_email"] == (
            "succeeded" if decision == "approve" else "rejected"
        )
        appr = await db.scalar(select(Approval).where(Approval.agent_run_id == run.id))
        assert appr.status == ("approved" if decision == "approve" else "rejected")
        answer = await db.scalar(select(Message).where(Message.agent_run_id == run.id, Message.role == "assistant"))
        assert answer.content.startswith("Sent" if decision == "approve" else "Not sent")
        await db.delete(await db.get(Conversation, convo_id))
        await db.commit()


async def test_direct_answer_needs_no_tools():
    llm = ScriptedLLM(
        {"summary": "greet", "needs_tools": False, "capabilities": [], "steps": []},
        [LLMResponse("Hello!")],
    )
    runner, bus, convo_id = await _setup(llm, FakeRegistry())
    _, run = await runner.start(convo_id, "hi")
    events = await _drain(bus, str(run.id))
    assert events[-1]["status"] == "completed"
    assert next(e for e in events if e["type"] == "message")["message"]["content"] == "Hello!"
    async with SessionLocal() as db:
        await db.delete(await db.get(Conversation, convo_id))
        await db.commit()
