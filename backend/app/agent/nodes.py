"""LangGraph nodes. Each node is one stage of the agent loop:

understand -> plan -> agent -> policy -> (approval) -> execute -> observe -> agent ... -> finalize
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.types import interrupt
from sqlalchemy import select

from app.agent.events import Emitter
from app.agent.policy import PolicyEngine
from app.agent.prompts import FINALIZE_PROMPT, PLAN_SCHEMA, agent_system_prompt, plan_prompt
from app.agent.state import AgentState, PendingCall
from app.agent.tools import REQUEST_CAPABILITY, SEP, ToolOutput, ToolRegistry, summarize_args
from app.config import Settings
from app.db.models import AgentRun, Approval, Document, ToolCall
from app.db.session import SessionLocal
from app.llm.base import LLMProvider

log = logging.getLogger(__name__)

MAX_CONSECUTIVE_ERRORS = 3
MAX_REPLANS = 2
# After this many redundant read-only lookups (same query or same results), stop the
# loop and force a final answer — small models otherwise re-search indefinitely.
MAX_REDUNDANT_LOOKUPS = 2

# Friendly activity labels; anything else falls back to "Using <tool>".
_LABELS = {
    "documents__search_documents": "Searching documents",
    "documents__retrieve_document": "Reading document",
    "documents__get_document_context": "Expanding document context",
    "file__list_files": "Listing workspace",
    "file__search_files": "Searching workspace",
    "file__read_file": "Reading {path}",
    "file__write_file": "Writing {path}",
    "file__create_file": "Creating {path}",
    "file__delete_file": "Deleting {path}",
    "web__search_web": "Searching web",
    "web__read_page": "Reading web page",
    "web__open_url": "Opening URL",
    "email__search_emails": "Searching email",
    "email__read_email": "Reading email",
    "email__find_contact": "Finding contact {name}",
    "email__draft_email": "Drafting email",
    "email__send_email": "Sending email",
    "email__reply_email": "Replying to email",
    "browser__navigate": "Browsing {url}",
    "browser__read_page": "Reading browser page",
    "browser__click": "Clicking in browser",
    "browser__type": "Typing in browser",
}


def activity_label(name: str, args: dict[str, Any]) -> str:
    template = _LABELS.get(name)
    if template is None:
        return f"Using {name.replace(SEP, ' · ')}"
    try:
        return template.format(**{k: str(v)[:60] for k, v in args.items()})
    except (KeyError, IndexError):
        return re.sub(r"\s*\{.*?\}", "", template)


@dataclass
class AgentDeps:
    llm: LLMProvider
    registry: ToolRegistry
    policy: PolicyEngine
    emitter: Emitter
    settings: Settings


class AgentNodes:
    def __init__(self, deps: AgentDeps):
        self.d = deps

    # ------------------------------------------------------------ understand
    async def understand(self, state: AgentState) -> dict[str, Any]:
        await self.d.emitter.step(state["run_id"], "understand", "Understanding request")
        async with SessionLocal() as db:
            docs = (await db.scalars(select(Document.filename).where(Document.status == "ready"))).all()
        return {
            "documents": list(docs),
            "available_capabilities": self.d.registry.available_capabilities(),
            "step_count": 0,
            "consecutive_errors": 0,
            "replans": 0,
            "citations": [],
            "rejected": False,
        }

    # ------------------------------------------------------------ plan
    async def plan(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        replanning = state.get("consecutive_errors", 0) >= MAX_CONSECUTIVE_ERRORS
        seq = await self.d.emitter.step(run_id, "plan", "Re-planning" if replanning else "Planning", "running")
        available = state["available_capabilities"]
        reason = None
        if replanning:
            errors = [m["content"][:300] for m in state.get("messages", []) if m["role"] == "tool"][-3:]
            reason = " | ".join(errors)
        messages = [
            {"role": "system", "content": plan_prompt(available, state.get("documents", []), reason)},
            *state.get("history", [])[-4:],
            {"role": "user", "content": state["goal"]},
        ]
        try:
            plan = await self.d.llm.complete_json(messages, PLAN_SCHEMA, name="plan")
            caps = [c for c in plan.get("capabilities", []) if c in available]
            if plan.get("needs_tools") and not caps:
                caps = available
            # Private-document search is read-only and cheap. Whenever documents are
            # indexed and the run will use tools, keep `documents` reachable so the agent
            # searches them instead of claiming "I don't have access" — the most common
            # small-model failure on questions about the user's own files.
            if plan.get("needs_tools") and state.get("documents") and "documents" in available and "documents" not in caps:
                caps = [*caps, "documents"]
        except Exception as e:  # noqa: BLE001 - a bad plan must not kill the run
            log.warning("Planning failed, using all capabilities: %s", e)
            plan, caps = {"summary": state["goal"], "needs_tools": True, "steps": []}, available
        plan["capabilities"] = caps
        await self.d.emitter.step(
            run_id, "plan", "Re-planned" if replanning else "Planned", "done",
            {"steps": plan.get("steps", []), "capabilities": caps}, seq=seq,
        )
        async with SessionLocal() as db:
            run = await db.get(AgentRun, uuid.UUID(run_id))
            run.plan = plan
            await db.commit()
        return {
            "plan": plan,
            "capabilities": caps,
            "consecutive_errors": 0,
            "replans": state.get("replans", 0) + (1 if replanning else 0),
        }

    # ------------------------------------------------------------ agent (LLM)
    def _llm_messages(self, state: AgentState) -> list[dict[str, Any]]:
        system = agent_system_prompt(state.get("plan", {}), state.get("documents", []), str(self.d.settings.file_workspace))
        return [
            {"role": "system", "content": system},
            *state.get("history", []),
            {"role": "user", "content": state["goal"]},
            *state.get("messages", []),
        ]

    async def agent(self, state: AgentState) -> dict[str, Any]:
        caps = state.get("capabilities", [])
        # The plan gates the action tools, but read-only lookup (document + web search)
        # is always available so the agent can check instead of claiming "no access".
        schemas = self.d.registry.schemas_for(caps)
        seen = {s["function"]["name"] for s in schemas}
        for s in self.d.registry.lookup_schemas():
            if s["function"]["name"] not in seen:
                schemas.append(s)
        tools = schemas or None
        resp = await self.d.llm.chat(self._llm_messages(state), tools=tools)
        update: dict[str, Any] = {"messages": [resp.as_message()]}
        if resp.tool_calls:
            update["pending"] = [
                PendingCall(call_id=tc.id, name=tc.name, arguments=tc.arguments, parse_error=tc.parse_error)
                for tc in resp.tool_calls
            ]
        else:
            update["pending"] = []
            update["final_answer"] = resp.content
        return update

    # ------------------------------------------------------------ policy check
    async def policy(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        specs = self.d.registry.specs()
        recent = "\n".join(m["content"] for m in state.get("messages", [])[-6:] if m["role"] == "tool")
        pending: list[PendingCall] = []
        async with SessionLocal() as db:
            for call in state.get("pending", []):
                spec = specs.get(call["name"])
                server = spec.capability if spec else "unknown"
                row = ToolCall(
                    agent_run_id=uuid.UUID(run_id), call_id=call["call_id"], server=server,
                    tool_name=call["name"], arguments=call["arguments"], status="pending",
                )
                db.add(row)
                await db.flush()
                call = PendingCall(**call, tool_call_db_id=str(row.id), approval_id=None, decision=None)
                if spec is not None and not call.get("parse_error"):
                    decision = await self.d.policy.evaluate(spec, call["arguments"], recent)
                    if decision.requires_approval:
                        approval = Approval(
                            agent_run_id=uuid.UUID(run_id), tool_call_id=row.id, kind=decision.kind,
                            action=call["name"], summary=decision.summary, reason=decision.reason,
                        )
                        db.add(approval)
                        await db.flush()
                        row.status = "awaiting_approval"
                        call["approval_id"], call["approval_kind"] = str(approval.id), decision.kind
                pending.append(call)
            await db.commit()
        for call in pending:
            if call["name"] != REQUEST_CAPABILITY.name:
                await self.d.emitter.step(
                    run_id, "tool_selected", f"Selected {call['name'].replace(SEP, ' · ')}",
                    detail={"tool": call["name"], "arguments": summarize_args(call["arguments"])},
                )
        return {"pending": pending}

    # ------------------------------------------------------------ human approval
    async def approval(self, state: AgentState) -> dict[str, Any]:
        # NOTE: this node re-runs from the top when resumed; nothing before
        # interrupt() may have side effects.
        needing = [c for c in state["pending"] if c.get("approval_id") and not c.get("decision")]
        if not needing:
            return {}
        decisions: dict[str, dict[str, Any]] = interrupt(
            {"approvals": [{"approval_id": c["approval_id"], "tool": c["name"], "kind": c.get("approval_kind")} for c in needing]}
        )
        pending, rejected = [], False
        for c in state["pending"]:
            c = dict(c)
            if c.get("approval_id"):
                d = decisions.get(c["approval_id"], {"decision": "reject", "note": "No decision"})
                c["decision"], c["note"] = d["decision"], d.get("note")
                rejected |= d["decision"] == "reject"
            pending.append(c)
        return {"pending": pending, "rejected": state.get("rejected", False) or rejected}

    # ------------------------------------------------------------ execute
    async def execute(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        messages, citations = [], list(state.get("citations", []))
        errors = state.get("consecutive_errors", 0)
        capabilities = list(state.get("capabilities", []))
        seen_sigs = set(state.get("tool_sigs", []))
        redundant = state.get("redundant_lookups", 0)
        specs = self.d.registry.specs()

        for call in state.get("pending", []):
            name, args = call["name"], call["arguments"]
            db_id = uuid.UUID(call["tool_call_db_id"])

            if call.get("parse_error"):
                text = f"Error: {call['parse_error']}. Call the tool again with valid JSON."
                await self._finish_call(db_id, "failed", text, 0)
                messages.append(_tool_msg(call, text))
                errors += 1
                continue

            if call.get("decision") == "reject":
                note = f" User note: {call['note']}" if call.get("note") else ""
                text = f"The user REJECTED this action; it was not performed. Do not retry it.{note}"
                await self._finish_call(db_id, "rejected", text, 0)
                await self.d.emitter.step(run_id, "approval", f"Rejected: {activity_label(name, args)}", "warning")
                messages.append(_tool_msg(call, text))
                continue

            if name == REQUEST_CAPABILITY.name:
                cap = args.get("capability")
                if cap in state.get("available_capabilities", []) and cap not in capabilities:
                    capabilities.append(cap)
                    text = f"Added {cap} tools: they are now available."
                    await self.d.emitter.step(run_id, "plan", f"Added capability: {cap}")
                else:
                    text = f"Capability '{cap}' is unavailable or already enabled."
                await self._finish_call(db_id, "succeeded", text, 0)
                messages.append(_tool_msg(call, text))
                continue

            label = activity_label(name, args)
            seq = await self.d.emitter.step(run_id, "tool", label, "running", {"tool": name})
            out = await self.d.registry.call(name, args)

            if out.data and "chunks" in out.data:
                text, citations = _number_chunks(out.data["chunks"], citations)
                out.text = out.text or text
                n = len(out.data["chunks"])
                detail = {"sources": sorted({c["filename"] for c in out.data["chunks"]})}
                await self.d.emitter.step(run_id, "rag", f"Retrieved {n} relevant chunk{'s' * (n != 1)}", detail=detail)

            for i, (img, mime) in enumerate(out.images):
                url = self._save_screenshot(run_id, img, mime, f"{seq}-{i}")
                self.d.emitter.event(run_id, "screenshot", url=url, tool=name)

            # Loop guard: a read-only lookup that repeats an earlier query or returns the
            # same passages means the model is spinning. Nudge it to answer, and count it
            # so route_after_execute can force a final answer.
            spec = specs.get(name)
            if spec and spec.read_only and not out.is_error:
                sig = _lookup_signature(name, args, out)
                if sig in seen_sigs:
                    redundant += 1
                    out.text += (
                        "\n\n[You already have this result from an earlier call. Do NOT search again — "
                        "answer the user now using the information above, citing [n] where relevant.]"
                    )
                seen_sigs.add(sig)

            status = "failed" if out.is_error else "succeeded"
            await self._finish_call(db_id, status, out.text, out.latency_ms)
            await self.d.emitter.step(
                run_id, "tool", label, "error" if out.is_error else "done",
                {"latency_ms": out.latency_ms, **({"error": out.text[:300]} if out.is_error else {})}, seq=seq,
            )
            errors = errors + 1 if out.is_error else 0
            messages.append(_tool_msg(call, out.text))

        return {
            "messages": messages,
            "pending": [],
            "citations": citations,
            "capabilities": capabilities,
            "consecutive_errors": errors,
            "tool_sigs": list(seen_sigs),
            "redundant_lookups": redundant,
            "step_count": state.get("step_count", 0) + 1,
        }

    async def _finish_call(self, db_id: uuid.UUID, status: str, result: str, latency_ms: int) -> None:
        async with SessionLocal() as db:
            row = await db.get(ToolCall, db_id)
            row.status, row.result, row.latency_ms = status, result[:20_000], latency_ms
            await db.commit()

    def _save_screenshot(self, run_id: str, data: bytes, mime: str, name: str) -> str:
        ext = "png" if "png" in mime else "jpg"
        folder: Path = self.d.settings.screenshots_dir / run_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.{ext}").write_bytes(data)
        return f"/api/runs/{run_id}/screenshots/{name}.{ext}"

    # ------------------------------------------------------------ finalize
    async def finalize(self, state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        answer = state.get("final_answer") or ""
        if not answer or state.get("pending"):
            # Step budget exhausted (or model returned nothing): force a summary without tools.
            msgs = [*self._llm_messages(state)]
            if msgs[-1].get("tool_calls"):
                msgs.pop()  # unanswered tool calls would be rejected by the API
            msgs.append({"role": "user", "content": FINALIZE_PROMPT})
            answer = (await self.d.llm.chat(msgs)).content or "I wasn't able to complete this task."
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
        citations = [c for c in state.get("citations", []) if c["n"] in cited] if cited else []
        if citations:
            await self.d.emitter.step(run_id, "verify", "Source verification complete",
                                      detail={"sources": len(citations)})
        await self.d.emitter.step(run_id, "complete", "Completed")
        return {"final_answer": answer, "citations": citations, "pending": []}


def _tool_msg(call: PendingCall, content: str) -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": call["call_id"], "content": content}


def _lookup_signature(name: str, args: dict[str, Any], out: ToolOutput) -> str:
    """Identity of a read-only lookup for loop detection. For document search, key on the
    returned chunk ids so different query wordings that return the same passages count as
    repeats; otherwise key on the arguments."""
    if out.data and "chunks" in out.data:
        ids = ",".join(sorted(c["chunk_id"] for c in out.data["chunks"]))
        return f"{name}:chunks={ids}"
    return f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"


def _number_chunks(chunks: list[dict[str, Any]], citations: list[dict[str, Any]]):
    """Give each retrieved chunk a stable citation number [n] across the whole run."""
    by_chunk = {c["chunk_id"]: c for c in citations}
    lines = []
    for ch in chunks:
        cit = by_chunk.get(ch["chunk_id"])
        if cit is None:
            cit = {
                "n": len(citations) + 1,
                "chunk_id": ch["chunk_id"],
                "document": ch["filename"],
                "document_id": ch["document_id"],
                "page": ch["page"],
                "section": ch["section"],
                "snippet": ch["content"][:280],
            }
            citations.append(cit)
            by_chunk[ch["chunk_id"]] = cit
        where = ", ".join(x for x in [f"page {ch['page']}" if ch["page"] else "", ch["section"] or ""] if x)
        lines.append(f"[{cit['n']}] {ch['filename']}{' (' + where + ')' if where else ''} chunk_id={ch['chunk_id']}\n{ch['content']}")
    return "\n\n---\n\n".join(lines), citations

