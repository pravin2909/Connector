// Typed client for the FastAPI backend (proxied at /api by Vite in dev).

export type RunStatus = 'pending' | 'running' | 'awaiting_approval' | 'completed' | 'failed' | 'cancelled'

export interface Conversation {
  id: string
  title: string
  color: string
  preview: string | null
  created_at: string
  updated_at: string
}

export interface Citation {
  n: number
  chunk_id: string
  document: string
  document_id: string
  page: number | null
  section: string | null
  snippet: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  agent_run_id: string | null
  citations: Citation[]
  created_at: string
}

export interface Step {
  seq: number
  kind: string
  label: string
  status: 'running' | 'done' | 'warning' | 'error'
  detail: Record<string, unknown> | null
  created_at?: string
}

export interface ToolCall {
  id: string
  server: string
  tool_name: string
  arguments: Record<string, unknown>
  result: string | null
  status: string
  latency_ms: number | null
  created_at: string
}

export interface Approval {
  id: string
  run_id: string
  kind: 'approval' | 'handoff'
  action: string
  summary: string
  reason: string
  status: 'pending' | 'approved' | 'rejected'
  note: string | null
  arguments: Record<string, unknown>
  created_at: string | null
}

export interface Run {
  id: string
  conversation_id: string
  goal: string
  status: RunStatus
  plan: { summary?: string; steps?: string[]; capabilities?: string[] } | null
  model: string | null
  error: string | null
  started_at: string
  completed_at: string | null
  duration_ms: number | null
  steps: Step[]
  tool_calls: ToolCall[]
  approvals: Approval[]
}

export interface ConversationDetail {
  conversation: Conversation
  messages: Message[]
  runs: Run[]
}

export interface DocumentInfo {
  id: string
  filename: string
  path: string
  file_type: string
  size: number
  status: 'queued' | 'processing' | 'ready' | 'failed'
  chunk_count: number
  page_count: number | null
  error: string | null
  created_at: string
}

export interface Health {
  database: boolean
  qdrant: boolean
  llm: { ok: boolean; model: string; loaded?: boolean; available?: string[]; error?: string }
  mcp: { name: string; status: string; error: string | null; tools: string[] }[]
  workspace: string
}

export interface Capability {
  capability: string
  description: string
  available: boolean
  tools: string[]
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { 'content-type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const api = {
  health: () => request<Health>('/health'),
  tools: () => request<Capability[]>('/tools'),

  conversations: () => request<Conversation[]>('/conversations'),
  createConversation: () => request<Conversation>('/conversations', { method: 'POST', body: '{}' }),
  conversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    request<Conversation>(`/conversations/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  deleteConversation: (id: string) => request<void>(`/conversations/${id}`, { method: 'DELETE' }),
  send: (id: string, content: string) =>
    request<{ message: Message; run: Run }>(`/conversations/${id}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),

  cancelRun: (id: string) => request<void>(`/runs/${id}/cancel`, { method: 'POST' }),
  decide: (approvalId: string, decision: 'approve' | 'reject', note?: string) =>
    request<Approval>(`/approvals/${approvalId}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision, note }),
    }),

  documents: () => request<DocumentInfo[]>('/documents'),
  uploadDocument: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentInfo>('/documents', { method: 'POST', body: form })
  },
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: 'DELETE' }),
}
