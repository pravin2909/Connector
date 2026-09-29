"""Policy engine: decides which tool calls are consequential and need a human decision."""

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.agent.tools import SEP, ToolRegistry, ToolSpec

RISKY_WORDS = re.compile(
    r"\b(submit|send|buy|pay|purchase|order|checkout|check out|confirm|delete|remove|post|publish|"
    r"sign ?up|register|transfer|book|subscribe|unsubscribe|place|accept|agree|approve)\b",
    re.IGNORECASE,
)
_REF_LINE = re.compile(r"^\[(\d+)\]\s+\S+\s+(.*)$", re.MULTILINE)


@dataclass
class PolicyDecision:
    requires_approval: bool
    reason: str = ""
    summary: str = ""
    kind: Literal["approval", "handoff"] = "approval"


class PolicyEngine:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def evaluate(
        self, spec: ToolSpec, args: dict[str, Any], recent_tool_text: str = ""
    ) -> PolicyDecision:
        name = spec.name
        if spec.read_only and name != f"browser{SEP}request_takeover":
            return PolicyDecision(False)

        if name in (f"email{SEP}send_email",):
            return PolicyDecision(True, "Sends an email", _email_summary(args))
        if name == f"email{SEP}reply_email":
            return PolicyDecision(True, "Sends an email reply", f"Reply to email #{args.get('email_id')}:\n\n{args.get('body', '')}")
        if name == f"file{SEP}delete_file":
            return PolicyDecision(True, "Deletes a file (moved to workspace trash)", f"Delete {args.get('path')}")
        if name == f"file{SEP}write_file":
            if await self._file_exists(args.get("path", "")):
                return PolicyDecision(
                    True, "Overwrites an existing file", f"Overwrite {args.get('path')}\n\n{str(args.get('content', ''))[:1500]}"
                )
            return PolicyDecision(False)
        if name == f"browser{SEP}request_takeover":
            return PolicyDecision(True, "Needs you in the browser", args.get("reason", "Please take over the browser."), "handoff")
        if spec.capability == "browser" and spec.tool in {"click", "type", "download"}:
            label = _element_label(args, recent_tool_text)
            if spec.tool == "type" and not args.get("submit"):
                return PolicyDecision(False)
            if label and RISKY_WORDS.search(label):
                return PolicyDecision(
                    True, "Submits a form / external side effect in the browser", f"Browser {spec.tool}: “{label}”"
                )
            return PolicyDecision(False)
        if spec.capability in {"file", "web", "browser", "documents", "meta"}:
            return PolicyDecision(False)
        # Tools from servers we don't know: trust the server's destructive hint.
        if spec.destructive:
            return PolicyDecision(True, "Tool is marked destructive", f"{name}({json.dumps(args)[:500]})")
        return PolicyDecision(False)

    async def _file_exists(self, path: str) -> bool:
        out = await self.registry.call(f"file{SEP}get_file_info", {"path": path})
        try:
            return bool(json.loads(out.text).get("exists"))
        except (json.JSONDecodeError, AttributeError):
            return True  # unknown -> be safe


def _email_summary(args: dict[str, Any]) -> str:
    lines = [f"To: {args.get('to')}"]
    if args.get("cc"):
        lines.append(f"Cc: {args['cc']}")
    lines.append(f"Subject: {args.get('subject')}")
    return "\n".join(lines) + f"\n\n{args.get('body', '')}"


def _element_label(args: dict[str, Any], recent_tool_text: str) -> str:
    if args.get("text"):
        return str(args["text"])
    if args.get("selector"):
        return str(args["selector"])
    if args.get("ref") is not None:
        refs = dict(_REF_LINE.findall(recent_tool_text))
        return refs.get(str(args["ref"]), "")
    return ""
