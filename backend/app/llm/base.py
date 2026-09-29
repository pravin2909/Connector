"""Provider-neutral LLM interface. The agent only depends on this module."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""
    parse_error: str | None = None


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str | None = None

    def as_message(self) -> dict[str, Any]:
        """OpenAI-format assistant message, stored in the agent transcript."""
        msg: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.raw_arguments or "{}"},
                }
                for tc in self.tool_calls
            ]
        return msg


class LLMProvider(Protocol):
    model: str

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse: ...

    async def complete_json(
        self, messages: list[dict[str, Any]], schema: dict[str, Any], name: str = "result"
    ) -> dict[str, Any]: ...

    async def list_models(self) -> list[str]: ...
