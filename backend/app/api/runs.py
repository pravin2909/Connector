import json
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.agent.runner import RunError, approval_dict
from app.api.conversations import run_detail
from app.api.deps import DB, ContainerDep
from app.api.schemas import DecisionIn, RunDetail
from app.db.models import AgentRun, Approval, ToolCall

router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: uuid.UUID, db: DB):
    run = await db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return await run_detail(db, run)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: uuid.UUID, request: Request, c: ContainerDep, db: DB):
    """Server-Sent Events stream of a run's live activity. Ends with a `done` event."""
    run = await db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    after = int(request.headers.get("last-event-id") or 0)

    async def gen():
        if run.status not in ("pending", "running") and not c.bus._history.get(str(run_id)):
            # Nothing live to stream; tell the client the final state immediately.
            yield {"event": "done", "data": json.dumps({"type": "done", "status": run.status})}
            return
        async for event in c.bus.subscribe(str(run_id), after):
            if await request.is_disconnected():
                return
            yield {"id": str(event["id"]), "event": event["type"], "data": json.dumps(event, default=str)}

    return EventSourceResponse(gen(), ping=15)


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel_run(run_id: uuid.UUID, c: ContainerDep, db: DB):
    run = await db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if run.status not in ("pending", "running", "awaiting_approval"):
        raise HTTPException(409, f"Run is already {run.status}")
    await c.runner.cancel(run_id)
    return {"status": "cancelling"}


@router.get("/runs/{run_id}/screenshots/{name}")
async def screenshot(run_id: uuid.UUID, name: str, c: ContainerDep):
    folder = (c.settings.screenshots_dir / str(run_id)).resolve()
    path = (folder / name).resolve()
    if not path.is_relative_to(folder) or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@router.get("/approvals")
async def list_approvals(db: DB, status: str | None = "pending"):
    q = select(Approval, ToolCall.arguments).join(ToolCall, ToolCall.id == Approval.tool_call_id)
    if status:
        q = q.where(Approval.status == status)
    rows = (await db.execute(q.order_by(Approval.created_at.desc()).limit(200))).all()
    return [approval_dict(a, args) for a, args in rows]


@router.post("/approvals/{approval_id}/decision")
async def decide(approval_id: uuid.UUID, body: DecisionIn, c: ContainerDep):
    try:
        appr = await c.runner.decide(approval_id, body.decision, body.note)
    except RunError as e:
        raise HTTPException(409, str(e)) from e
    return approval_dict(appr)
