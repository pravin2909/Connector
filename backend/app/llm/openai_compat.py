import json
import logging
import re
import uuid
from typing import Any

from openai import AsyncOpenAI, BadRequestError

from app.config import Settings
from app.llm.base import LLMResponse, ToolCallRequest

log = logging.getLogger(__name__)

# Reasoning models (Qwen3, DeepSeek-R1, ...) may emit hidden reasoning inline. It is
# never shown to the user or stored.
_THINK_RE = re.compile(r"<think>.*?(</think>|$)", re.DOTALL | re.IGNORECASE)
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def strip_reasoning(text: str | None) -> str:
    return _THINK_RE.sub("", text or "").strip()


def extract_json(text: str) -> dict[str, Any]:
    text = strip_reasoning(text)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            raise
        return json.loads(match.group(0))


class OpenAICompatibleProvider:
    """Talks to any OpenAI-compatible server (LM Studio, vLLM, Ollama, ...)."""

    def __init__(self, settings: Settings):
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "not-needed",
            timeout=settings.llm_timeout_s,
        )
        self._structured_output_supported = True

    async def chat(self, messages, tools=None, temperature=None) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = await self.client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        calls = []
        for tc in choice.message.tool_calls or []:
            raw = tc.function.arguments or "{}"
            try:
                args = json.loads(raw) if raw.strip() else {}
                err = None if isinstance(args, dict) else "arguments must be a JSON object"
            except json.JSONDecodeError as e:
                args, err = {}, f"invalid JSON arguments: {e}"
            calls.append(
                ToolCallRequest(
                    id=tc.id or f"call_{uuid.uuid4().hex[:12]}",
                    name=tc.function.name,
                    arguments=args if isinstance(args, dict) else {},
                    raw_arguments=raw,
                    parse_error=err,
                )
            )
        return LLMResponse(
            content=strip_reasoning(choice.message.content),
            tool_calls=calls,
            finish_reason=choice.finish_reason,
        )

    async def complete_json(self, messages, schema, name="result") -> dict[str, Any]:
        """Structured output via JSON schema when the server supports it, else prompt + parse."""
        if self._structured_output_supported:
            try:
                resp = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": name, "schema": schema, "strict": True},
                    },
                )
                return extract_json(resp.choices[0].message.content or "")
            except BadRequestError:
                log.info("Structured output unsupported by %s; falling back to prompting", self.model)
                self._structured_output_supported = False
        hint = {
            "role": "system",
            "content": "Respond with ONLY a JSON object matching this schema, no prose:\n"
            + json.dumps(schema),
        }
        resp = await self.client.chat.completions.create(
            model=self.model, messages=[*messages, hint], temperature=0
        )
        return extract_json(resp.choices[0].message.content or "")

    async def list_models(self) -> list[str]:
        page = await self.client.models.list()
        return [m.id for m in page.data]
