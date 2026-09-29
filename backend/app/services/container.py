"""Builds and owns every long-lived service. Created once in the FastAPI lifespan."""

import asyncio
import logging
from contextlib import AsyncExitStack

from langgraph.checkpoint.memory import InMemorySaver

from app.agent.events import Emitter, EventBus
from app.agent.graph import build_graph
from app.agent.nodes import AgentDeps
from app.agent.policy import PolicyEngine
from app.agent.runner import AgentRunner
from app.agent.tools import ToolRegistry
from app.config import Settings
from app.llm.openai_compat import OpenAICompatibleProvider
from app.mcp_client import MCPManager, default_servers
from app.rag.service import RAGService

log = logging.getLogger(__name__)


class Container:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm = OpenAICompatibleProvider(settings)
        self.mcp = MCPManager(default_servers(settings))
        self.rag = RAGService(settings)
        self.registry = ToolRegistry(self.mcp, self.rag, settings.tool_result_max_chars)
        self.policy = PolicyEngine(self.registry)
        self.bus = EventBus()
        self.emitter = Emitter(self.bus)
        self._stack = AsyncExitStack()
        self._background: set[asyncio.Task] = set()
        self.graph = None
        self.runner: AgentRunner | None = None

    async def start(self) -> None:
        s = self.settings
        s.file_workspace.mkdir(parents=True, exist_ok=True)
        s.documents_dir.mkdir(parents=True, exist_ok=True)
        s.screenshots_dir.mkdir(parents=True, exist_ok=True)

        durable = s.checkpointer == "postgres"
        if durable:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            checkpointer = await self._stack.enter_async_context(AsyncPostgresSaver.from_conn_string(s.checkpointer_dsn))
            await checkpointer.setup()
        else:
            checkpointer = InMemorySaver()

        await self.mcp.start()
        deps = AgentDeps(self.llm, self.registry, self.policy, self.emitter, s)
        self.graph = build_graph(deps, checkpointer)
        self.runner = AgentRunner(self.graph, self.bus, self.emitter, self.llm.model, s.agent_history_messages, self.llm)
        await AgentRunner.recover_after_restart(durable)

    async def stop(self) -> None:
        for t in list(self._background):
            t.cancel()
        await self.mcp.close()
        await self._stack.aclose()

    def background(self, coro) -> None:
        """Fire-and-forget with a strong reference so the task isn't garbage collected."""
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
