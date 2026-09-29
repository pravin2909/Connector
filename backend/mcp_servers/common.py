import functools
import inspect
import logging
import sys

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

# stdout is the MCP transport; logs must go to stderr.
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s %(message)s")


def _as_tool_error(e: Exception) -> ToolError:
    return e if isinstance(e, ToolError) else ToolError(f"{type(e).__name__}: {e}")


def register(server: MCPServer, *, read_only: bool = False, destructive: bool = False, open_world: bool = False):
    """@server.tool() that surfaces exception messages to the agent and sets MCP annotations.

    The annotations are informational; the backend policy engine makes the actual
    approval decision.
    """
    annotations = ToolAnnotations(
        read_only_hint=read_only, destructive_hint=destructive, open_world_hint=open_world
    )

    def decorator(fn):
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                try:
                    return await fn(*args, **kwargs)
                except Exception as e:
                    raise _as_tool_error(e) from e
        else:

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    raise _as_tool_error(e) from e

        server.tool(annotations=annotations)(wrapper)
        return fn

    return decorator
