import json

from fastapi import APIRouter
from sqlalchemy import text

from app.agent.tools import CAPABILITIES
from app.api.deps import DB, ContainerDep

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(c: ContainerDep, db: DB):
    try:
        await db.execute(text("select 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    try:
        models = await c.llm.list_models()
        llm = {"ok": True, "model": c.llm.model, "loaded": c.llm.model in models, "available": models}
    except Exception as e:  # noqa: BLE001
        llm = {"ok": False, "model": c.llm.model, "error": type(e).__name__}
    return {
        "database": db_ok,
        "qdrant": await c.rag.store.ping(),
        "llm": llm,
        "mcp": c.mcp.status(),
        "workspace": str(c.settings.file_workspace),
    }


@router.get("/tools")
async def tools(c: ContainerDep):
    specs = c.registry.specs().values()
    return [
        {
            "capability": cap,
            "description": desc,
            "available": cap in c.registry.available_capabilities(),
            "tools": [s.tool for s in specs if s.capability == cap],
        }
        for cap, desc in CAPABILITIES.items()
    ]


@router.get("/files")
async def files(c: ContainerDep, path: str = "."):
    """Workspace browser for the UI - served through the File MCP like everything else."""
    out = await c.registry.call("file__list_files", {"path": path})
    if out.is_error:
        return {"error": out.text, "items": []}
    return json.loads(out.text)
