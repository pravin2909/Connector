import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import conversations, documents, runs, system
from app.config import get_settings
from app.db.session import ensure_local_user
from app.services.container import Container

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await ensure_local_user()
    container = Container(settings)
    await container.start()
    app.state.container = container
    try:
        yield
    finally:
        await container.stop()


app = FastAPI(title="Connecter", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (system.router, conversations.router, runs.router, documents.router):
    app.include_router(r, prefix="/api")
