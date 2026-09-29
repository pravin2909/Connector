"""Run lifecycle: start a run in the background, stream events, pause for approval, resume."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from langgraph.types import Command
from sqlalchemy import select, update

from app.agent.events import Emitter, EventBus
from app.db.models import AgentRun, Approval, Conversation, Message, ToolCall
from app.db.session import SessionLocal

log = logging.getLogger(__name__)

ACTIVE = ("pending", "running", "awaiting_approval")


class RunError(Exception):
    pass


class AgentRunner:
    def __init__(self, graph, bus: EventBus, emitter: Emitter, model: str, history_messages: int, llm=None):
        self.graph = graph
        self.bus = bus
        self.emitter = emitter
        self.model = model
        self.history_messages = history_messages
        self.llm = llm
        self._tasks: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------ start
    async def start(self, conversation_id: uuid.UUID, content: str) -> tuple[Message, AgentRun]:
        async with SessionLocal() as db:
            convo = await db.get(Conversation, conversation_id)
            if convo is None:
                raise RunError("Conversation not found")
            busy = await db.scalar(
                select(AgentRun.id).where(AgentRun.conversation_id == conversation_id, AgentRun.status.in_(ACTIVE))
            )
            if busy:
                raise RunError("This conversation already has an active run. Wait for it or cancel it.")
            prior = (
                await db.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation_id, Message.role.in_(("user", "assistant")))
                    .order_by(Message.created_at.desc())
                    .limit(self.history_messages)
                )
            ).all()
            history = [{"role": m.role, "content": m.content} for m in reversed(prior)]
            run = AgentRun(conversation_id=conversation_id, goal=content, status="running", model=self.model)
            db.add(run)
            await db.flush()
            msg = Message(conversation_id=conversation_id, role="user", content=content, agent_run_id=run.id)
            db.add(msg)
            first_turn = not prior
            convo.preview = content[:280]
            if first_turn and convo.title == "New chat":
                convo.title = _heuristic_title(content)
            await db.commit()
            await db.refresh(msg)
            await db.refresh(run)

        run_id = str(run.id)
        state = {"run_id": run_id, "goal": content, "history": history, "messages": [], "pending": []}
        self._spawn(run_id, state)
        if first_turn and self.llm is not None:
            asyncio.create_task(self._llm_title(conversation_id, content))
        return msg, run

    def _spawn(self, run_id: str, graph_input: Any) -> None:
        task = asyncio.create_task(self._drive(run_id, graph_input), name=f"run:{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))

    # ------------------------------------------------------------------ drive
    async def _drive(self, run_id: str, graph_input: Any) -> None:
        config = {"configurable": {"thread_id": run_id}, "recursion_limit": 200}
        self.emitter.event(run_id, "status", status="running")
        try:
            async for chunk in self.graph.astream(graph_input, config, stream_mode="updates"):
                if "__interrupt__" in chunk:
                    break
            snapshot = await self.graph.aget_state(config)
            if snapshot.next:  # paused at an interrupt -> waiting for the human
                await self._set_status(run_id, "awaiting_approval")
                approvals = await self._pending_approvals(run_id)
                for a in approvals:
                    await self.emitter.step(
                        run_id, "approval",
                        "Takeover requested" if a["kind"] == "handoff" else f"Approval required: {a['action'].replace('__', ' · ')}",
                        "warning", {"approval_id": a["id"]},
                    )
                self.emitter.event(run_id, "approval_required", approvals=approvals)
                self.emitter.event(run_id, "status", status="awaiting_approval")
                self.emitter.event(run_id, "done", status="awaiting_approval")
                return
            await self._complete(run_id, snapshot.values)
        except asyncio.CancelledError:
            await self._set_status(run_id, "cancelled", finished=True)
            self.emitter.event(run_id, "status", status="cancelled")
            self.emitter.event(run_id, "done", status="cancelled")
            raise
        except Exception as e:
            log.exception("Run %s failed", run_id)
            await self._set_status(run_id, "failed", finished=True, error=_friendly_error(e))
            await self.emitter.step(run_id, "error", "Run failed", "error", {"error": _friendly_error(e)})
            self.emitter.event(run_id, "error", message=_friendly_error(e))
            self.emitter.event(run_id, "done", status="failed")

    async def _complete(self, run_id: str, values: dict[str, Any]) -> None:
        answer = values.get("final_answer") or ""
        async with SessionLocal() as db:
            run = await db.get(AgentRun, uuid.UUID(run_id))
            msg = Message(
                conversation_id=run.conversation_id, role="assistant", content=answer,
                agent_run_id=run.id, citations=values.get("citations", []),
            )
            db.add(msg)
            convo = await db.get(Conversation, run.conversation_id)
            convo.preview = answer[:280]
            await db.commit()
            await db.refresh(msg)
        await self._set_status(run_id, "completed", finished=True)
        self.emitter.event(run_id, "message", message=message_dict(msg))
        self.emitter.event(run_id, "status", status="completed")
        self.emitter.event(run_id, "done", status="completed")

    # ------------------------------------------------------------------ approvals
    async def decide(self, approval_id: uuid.UUID, decision: str, note: str | None) -> Approval:
        if decision not in {"approve", "reject"}:
            raise RunError("decision must be 'approve' or 'reject'")
        async with SessionLocal() as db:
            appr = await db.get(Approval, approval_id)
            if appr is None:
                raise RunError("Approval not found")
            run_id = str(appr.agent_run_id)
        lock = self._locks.setdefault(run_id, asyncio.Lock())
        async with lock:
            async with SessionLocal() as db:
                appr = await db.get(Approval, approval_id)
                if appr.status != "pending":
                    raise RunError(f"Approval already {appr.status}")
                appr.status = "approved" if decision == "approve" else "rejected"
                appr.note, appr.decided_at = note, datetime.now(UTC)
                await db.commit()
                await db.refresh(appr)
            self.emitter.event(run_id, "approval_resolved", approval_id=str(approval_id), status=appr.status)
            remaining = await self._pending_approvals(run_id)
            if remaining:
                return appr
            async with SessionLocal() as db:
                run = await db.get(AgentRun, uuid.UUID(run_id))
                if run.status != "awaiting_approval":
                    return appr
                run.status = "running"
                await db.commit()
            resume = await self._decisions_for_interrupt(run_id)
            self.bus.reset(run_id)
            self._spawn(run_id, Command(resume=resume))
        return appr

    async def _decisions_for_interrupt(self, run_id: str) -> dict[str, dict[str, Any]]:
        snapshot = await self.graph.aget_state({"configurable": {"thread_id": run_id}})
        ids = [
            a["approval_id"]
            for task in snapshot.tasks
            for intr in task.interrupts
            for a in intr.value.get("approvals", [])
        ]
        async with SessionLocal() as db:
            rows = (await db.scalars(select(Approval).where(Approval.id.in_([uuid.UUID(i) for i in ids])))).all()
        return {
            str(r.id): {"decision": "approve" if r.status == "approved" else "reject", "note": r.note} for r in rows
        }

    async def _pending_approvals(self, run_id: str) -> list[dict[str, Any]]:
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    select(Approval, ToolCall.arguments)
                    .join(ToolCall, ToolCall.id == Approval.tool_call_id)
                    .where(Approval.agent_run_id == uuid.UUID(run_id), Approval.status == "pending")
                    .order_by(Approval.created_at)
                )
            ).all()
        return [approval_dict(a, args) for a, args in rows]

    # ------------------------------------------------------------------ cancel / recovery
    async def cancel(self, run_id: uuid.UUID) -> None:
        rid = str(run_id)
        task = self._tasks.get(rid)
        if task:
            task.cancel()
            return
        # Not executing (e.g. waiting for approval): cancel in the DB.
        async with SessionLocal() as db:
            await db.execute(
                update(Approval).where(Approval.agent_run_id == run_id, Approval.status == "pending")
                .values(status="rejected", note="Run cancelled", decided_at=datetime.now(UTC))
            )
            await db.commit()
        await self._set_status(rid, "cancelled", finished=True)
        self.emitter.event(rid, "status", status="cancelled")
        self.emitter.event(rid, "done", status="cancelled")

    @staticmethod
    async def recover_after_restart(durable_checkpoints: bool) -> None:
        """Runs that were executing when the server stopped cannot continue. Runs waiting
        for approval can, if checkpoints are durable."""
        stale = ("pending", "running") if durable_checkpoints else ACTIVE
        async with SessionLocal() as db:
            await db.execute(
                update(AgentRun).where(AgentRun.status.in_(stale))
                .values(status="failed", error="Interrupted by a server restart", completed_at=datetime.now(UTC))
            )
            await db.commit()

    async def _set_status(self, run_id: str, status: str, finished: bool = False, error: str | None = None) -> None:
        async with SessionLocal() as db:
            run = await db.get(AgentRun, uuid.UUID(run_id))
            run.status = status
            if error:
                run.error = error
            if finished:
                run.completed_at = datetime.now(UTC)
                run.duration_ms = int((run.completed_at - run.started_at).total_seconds() * 1000)
            await db.commit()

    async def _llm_title(self, conversation_id: uuid.UUID, content: str) -> None:
        try:
            resp = await self.llm.chat(
                [
                    {"role": "system", "content": "Give a 2-4 word title for this task. Reply with the title only, no quotes."},
                    {"role": "user", "content": content[:1000]},
                ],
                temperature=0,
            )
            title = resp.content.strip().strip('"').splitlines()[0][:60] if resp.content else ""
            if title:
                async with SessionLocal() as db:
                    convo = await db.get(Conversation, conversation_id)
                    convo.title = title
                    await db.commit()
        except Exception:
            log.debug("Title generation failed", exc_info=True)


def _heuristic_title(text: str) -> str:
    words = text.split()
    return (" ".join(words[:5]) + ("…" if len(words) > 5 else ""))[:60] or "New chat"


def _friendly_error(e: Exception) -> str:
    name = type(e).__name__
    if name in {"APIConnectionError", "ConnectError"}:
        return "Can't reach the local LLM. Is LM Studio running with the server started?"
    return f"{name}: {e}"[:500]


def message_dict(m: Message) -> dict[str, Any]:
    return {
        "id": str(m.id), "role": m.role, "content": m.content, "citations": m.citations or [],
        "agent_run_id": str(m.agent_run_id) if m.agent_run_id else None, "created_at": m.created_at.isoformat(),
    }


def approval_dict(a: Approval, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": str(a.id), "run_id": str(a.agent_run_id), "kind": a.kind, "action": a.action,
        "summary": a.summary, "reason": a.reason, "status": a.status, "note": a.note,
        "arguments": arguments or {}, "created_at": a.created_at.isoformat() if a.created_at else None,
    }
