"""Live run events: persisted as agent_steps and fanned out to SSE subscribers."""

import asyncio
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import func, select

from app.db.models import AgentStep
from app.db.session import SessionLocal

TERMINAL = {"done"}


class EventBus:
    def __init__(self, history_limit: int = 500):
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._limit = history_limit

    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        hist = self._history[run_id]
        event = {**event, "id": (hist[-1]["id"] + 1) if hist else 1}
        hist.append(event)
        del hist[: -self._limit]
        for q in list(self._subs[run_id]):
            q.put_nowait(event)

    async def subscribe(self, run_id: str, after_id: int = 0) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue = asyncio.Queue()
        self._subs[run_id].add(q)
        try:
            for e in list(self._history[run_id]):
                if e["id"] > after_id:
                    yield e
                    if e["type"] in TERMINAL:
                        return
            while True:
                e = await q.get()
                if e["id"] > after_id:
                    yield e
                    if e["type"] in TERMINAL:
                        return
        finally:
            self._subs[run_id].discard(q)

    def reset(self, run_id: str) -> None:
        """Called when a run resumes after approval so old 'done' events don't end new streams."""
        self._history[run_id] = [e for e in self._history[run_id] if e["type"] not in TERMINAL]


class Emitter:
    """What graph nodes use to report safe, high-level progress (never chain-of-thought)."""

    def __init__(self, bus: EventBus):
        self.bus = bus

    async def step(
        self,
        run_id: str,
        kind: str,
        label: str,
        status: str = "done",
        detail: dict[str, Any] | None = None,
        seq: int | None = None,
    ) -> int:
        """Create a step, or update it when `seq` is given. Returns the step seq."""
        rid = uuid.UUID(run_id)
        async with SessionLocal() as db:
            if seq is None:
                seq = (await db.scalar(select(func.max(AgentStep.seq)).where(AgentStep.agent_run_id == rid)) or 0) + 1
                db.add(AgentStep(agent_run_id=rid, seq=seq, kind=kind, label=label, status=status, detail=detail))
            else:
                row = await db.scalar(select(AgentStep).where(AgentStep.agent_run_id == rid, AgentStep.seq == seq))
                if row is not None:
                    row.label, row.status = label, status
                    if detail is not None:
                        row.detail = {**(row.detail or {}), **detail}
            await db.commit()
        self.bus.publish(
            run_id, {"type": "step", "step": {"seq": seq, "kind": kind, "label": label, "status": status, "detail": detail}}
        )
        return seq

    def event(self, run_id: str, type_: str, **payload: Any) -> None:
        self.bus.publish(run_id, {"type": type_, **payload})
