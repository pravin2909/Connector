# Connecter

A local-first AI computer agent. It plans multi-step tasks, uses your private documents (agentic RAG), the web, local files, email and a real browser through MCP servers, and pauses for your approval before doing anything consequential.

```
React + TS (Vite, Tailwind, TanStack Query)
        │  HTTP + SSE  (/api, proxied by Vite in dev)
FastAPI ── LangGraph agent ── MCP client ──┬── File MCP     → ~/AI-Agent-Workspace (sandboxed)
   │            │                          ├── Web MCP      → search + page reading (SSRF-guarded)
   │            │                          ├── Email MCP    → IMAP/SMTP
   │            └── RAG tools              └── Browser MCP  → Playwright (persistent profile)
   │                 └── fastembed (bge-small + BM25) → Qdrant (hybrid, RRF) → cross-encoder rerank
   ├── PostgreSQL  (users, sessions, conversations, messages, runs, steps, tool calls, approvals, documents)
   └── LM Studio   (OpenAI-compatible; model chosen in .env)
```

## Run it

Prerequisites: Docker, Python 3.11+, Node 20+, and [LM Studio](https://lmstudio.ai) with a tool-calling model loaded (e.g. Qwen 2.5 14B Instruct) and its local server started.

```bash
cp .env.example .env            # set LLM_MODEL to the model id LM Studio shows; email creds optional
docker compose up -d            # Postgres on :5433, Qdrant on :6333

cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/playwright install chromium
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --port 8010 --reload

cd ../frontend && npm install && npm run dev    # http://localhost:5173
```

The first document you upload downloads the embedding and reranker models (~200 MB, once).

Tests: `cd backend && .venv/bin/pytest` (the agent-loop tests use the Postgres from docker compose).

## How a run works

`understand → plan → agent ⇄ (policy → approval? → execute → observe) → finalize`, one LangGraph node per stage (`backend/app/agent/`).

- **Plan** picks which capabilities the task needs, and only those tools are bound to the LLM. This keeps small local models accurate. The agent can call `request_capability` to add more mid-run, and three consecutive tool errors trigger a re-plan.
- **Policy** (`agent/policy.py`) classifies each tool call. The following pause the run through a LangGraph `interrupt()`:
  - `send_email` and `reply_email`
  - `delete_file`
  - `write_file` onto an existing file
  - browser clicks on submit/buy/send-style elements
  - `request_takeover` (the "Take over / I'm done" card)

  Checkpoints live in Postgres, so a pending approval survives a backend restart.
- **Activity**: every stage emits safe, high-level steps (never chain-of-thought). They are stored in `agent_steps` and streamed over SSE (`GET /api/runs/{id}/events`).
- **RAG citations**: retrieved passages are numbered `[n]` across the whole run. The final answer keeps only the sources it actually cites.

## Key API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/conversations/{id}/messages` | start a run |
| GET | `/api/runs/{id}/events` | SSE live activity |
| POST | `/api/approvals/{id}/decision` | `{"decision": "approve" \| "reject"}` |
| POST | `/api/documents` | upload + index a document |
| POST | `/api/documents/search` | inspect the retrieval pipeline |
| GET | `/api/health` | DB, Qdrant, LLM and MCP server status |
