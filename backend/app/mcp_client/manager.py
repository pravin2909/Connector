"""MCP client: spawns each MCP server over stdio and keeps a live session to it.

The agent never touches files, email, the web or the browser directly - it asks this
manager to call a tool, and the MCP server performs the operation.
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any

from mcp import Client, StdioServerParameters
from mcp import types as mcp_types

from app.config import BACKEND_DIR, Settings

log = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    name: str
    module: str
    env: dict[str, str] = field(default_factory=dict)
    timeout_s: float = 120


def default_servers(s: Settings) -> list[ServerConfig]:
    common = {"FILE_WORKSPACE": str(s.file_workspace)}
    return [
        ServerConfig("file", "mcp_servers.file_server", common),
        ServerConfig("web", "mcp_servers.web_server", common),
        ServerConfig(
            "email",
            "mcp_servers.email_server",
            {
                "EMAIL_ADDRESS": s.email_address,
                "EMAIL_PASSWORD": s.email_password,
                "EMAIL_IMAP_HOST": s.email_imap_host,
                "EMAIL_IMAP_PORT": str(s.email_imap_port),
                "EMAIL_SMTP_HOST": s.email_smtp_host,
                "EMAIL_SMTP_PORT": str(s.email_smtp_port),
                "EMAIL_DRAFTS_FOLDER": s.email_drafts_folder,
            },
        ),
        ServerConfig(
            "browser",
            "mcp_servers.browser_server",
            {**common, "BROWSER_HEADLESS": str(s.browser_headless).lower(),
             "BROWSER_PROFILE_DIR": str(s.data_dir / "browser-profile")},
            timeout_s=180,
        ),
    ]


@dataclass
class ServerHandle:
    config: ServerConfig
    client: Client | None = None
    tools: list[mcp_types.Tool] = field(default_factory=list)
    status: str = "starting"  # starting | ready | failed | stopped
    error: str | None = None
    _ready: asyncio.Event = field(default_factory=asyncio.Event)
    _stop: asyncio.Event = field(default_factory=asyncio.Event)
    _task: asyncio.Task | None = None


class MCPManager:
    def __init__(self, servers: list[ServerConfig]):
        self.servers = {c.name: ServerHandle(c) for c in servers}

    async def start(self, wait_s: float = 30) -> None:
        for handle in self.servers.values():
            handle._task = asyncio.create_task(self._run(handle), name=f"mcp:{handle.config.name}")
        await asyncio.wait([asyncio.create_task(h._ready.wait()) for h in self.servers.values()], timeout=wait_s)
        for h in self.servers.values():
            log.info("MCP server %-8s %s %s", h.config.name, h.status, h.error or f"({len(h.tools)} tools)")

    async def _run(self, h: ServerHandle) -> None:
        # The stdio transport's context must be entered and exited in the same task,
        # so each server lives in its own long-running task.
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", h.config.module],
            env={**os.environ, **h.config.env},
            cwd=str(BACKEND_DIR),
        )
        try:
            async with Client(params, read_timeout_seconds=h.config.timeout_s) as client:
                h.client = client
                h.tools = (await client.list_tools()).tools
                h.status, h.error = "ready", None
                h._ready.set()
                await h._stop.wait()
        except Exception as e:
            log.exception("MCP server %s failed", h.config.name)
            h.status, h.error = "failed", str(e)
        finally:
            h.client = None
            if h.status != "failed":
                h.status = "stopped"
            h._ready.set()

    async def close(self) -> None:
        for h in self.servers.values():
            h._stop.set()
        tasks = [h._task for h in self.servers.values() if h._task]
        if tasks:
            await asyncio.wait(tasks, timeout=10)

    def tools(self) -> dict[str, list[mcp_types.Tool]]:
        return {name: h.tools for name, h in self.servers.items() if h.status == "ready"}

    def status(self) -> list[dict[str, Any]]:
        return [
            {"name": n, "status": h.status, "error": h.error, "tools": [t.name for t in h.tools]}
            for n, h in self.servers.items()
        ]

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> mcp_types.CallToolResult:
        h = self.servers.get(server)
        if h is None or h.client is None:
            raise RuntimeError(f"MCP server '{server}' is not available ({h.error if h else 'unknown'})")
        return await h.client.call_tool(tool, arguments)
