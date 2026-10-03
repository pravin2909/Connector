import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useMemo, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { keys, useConversations, useDocuments, useHealth, useUploadDocument } from '../../lib/hooks'
import { useUI } from '../../store'
import { Logo } from '../../pages/Home'
import {
  ChevronIcon,
  ComposeIcon,
  DocIcon,
  SearchIcon,
  SettingsIcon,
  SidebarIcon,
  TrashIcon,
} from '../icons'
import { Popover } from '../Popover'
import { ThemeToggle } from '../ThemeToggle'

const CAP_LABELS: Record<string, string> = {
  file: 'Files (workspace)',
  web: 'Web',
  email: 'Email',
  browser: 'Browser',
}

export function Rail() {
  const expanded = useUI((s) => s.sidebarExpanded)
  return expanded ? <ExpandedSidebar /> : <CollapsedRail />
}

/* ----------------------------------------------------------------- expanded */

function ExpandedSidebar() {
  const { data: conversations = [] } = useConversations()
  const { conversationId, selectConversation, toggleSidebar } = useUI()
  const qc = useQueryClient()
  const [query, setQuery] = useState('')

  const create = useMutation({
    mutationFn: api.createConversation,
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: keys.conversations })
      selectConversation(c.id)
    },
  })

  const filtered = useMemo(() => {
    const t = query.trim().toLowerCase()
    if (!t) return conversations
    return conversations.filter((c) => (c.title + ' ' + (c.preview ?? '')).toLowerCase().includes(t))
  }, [conversations, query])

  return (
    <div className="flex w-[264px] shrink-0 flex-col border-r border-line bg-bg2">
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <Logo className="!text-[20px]" />
        <IconBtn title="Collapse sidebar" onClick={toggleSidebar}>
          <SidebarIcon className="size-[17px]" />
        </IconBtn>
      </div>

      <div className="px-2">
        <button
          onClick={() => create.mutate()}
          className="flex w-full items-center gap-2.5 rounded-[10px] px-2.5 py-2.5 text-[14px] font-medium text-ink transition hover:bg-hover"
        >
          <ComposeIcon className="size-[18px]" />
          New chat
        </button>
      </div>

      <div className="px-3 pt-1.5">
        <div className="flex items-center gap-2 rounded-[10px] border border-line bg-panel px-2.5 py-2 focus-within:border-faint">
          <SearchIcon className="size-4 shrink-0 text-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats…"
            className="w-full bg-transparent text-[13px] text-ink outline-none placeholder:text-faint"
          />
        </div>
      </div>

      <div className="mt-3 flex-1 overflow-y-auto px-2 pb-2">
        <div className="px-2 pb-1.5 text-[11px] font-medium tracking-wide text-faint uppercase">
          {query ? 'Results' : 'Chats'}
        </div>
        {filtered.length === 0 ? (
          <div className="px-2 py-2 text-[12.5px] text-faint">{query ? 'No chats match.' : 'No chats yet.'}</div>
        ) : (
          filtered.map((c) => (
            <ChatRow key={c.id} c={c} active={c.id === conversationId} onSelect={() => selectConversation(c.id)} />
          ))
        )}
      </div>

      <Footer />
    </div>
  )
}

function ChatRow({
  c,
  active,
  onSelect,
}: {
  c: { id: string; title: string; preview: string | null }
  active: boolean
  onSelect: () => void
}) {
  const { conversationId, selectConversation } = useUI()
  const qc = useQueryClient()
  const remove = useMutation({
    mutationFn: () => api.deleteConversation(c.id),
    onSuccess: () => {
      if (conversationId === c.id) selectConversation(null)
      qc.invalidateQueries({ queryKey: keys.conversations })
    },
  })

  return (
    <div
      className={`group flex items-center gap-1 rounded-[10px] pr-1 transition ${
        active ? 'bg-panel' : 'hover:bg-hover'
      }`}
    >
      <button onClick={onSelect} className="flex min-w-0 flex-1 items-center gap-2.5 py-2 pl-2.5 text-left">
        <span className={`size-1.5 shrink-0 rounded-full ${active ? 'bg-accent' : 'bg-faint'}`} />
        <span className={`truncate text-[13.5px] ${active ? 'text-ink' : 'text-muted group-hover:text-ink'}`}>
          {c.title}
        </span>
      </button>
      <button
        title="Delete chat"
        onClick={(e) => {
          e.stopPropagation()
          if (confirm(`Delete “${c.title}” and its history?`)) remove.mutate()
        }}
        className="flex size-7 shrink-0 items-center justify-center rounded-md text-faint opacity-0 transition group-hover:opacity-100 hover:text-danger"
      >
        <TrashIcon className="size-3.5" />
      </button>
    </div>
  )
}

/* ---------------------------------------------------------------- collapsed */

function CollapsedRail() {
  const { selectConversation, toggleSidebar } = useUI()
  const qc = useQueryClient()
  const create = useMutation({
    mutationFn: api.createConversation,
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: keys.conversations })
      selectConversation(c.id)
    },
  })

  return (
    // Collapsed: a slim toolbar that blends into the page (same bg, no divider) so it reads
    // as a floating rail — not a second panel next to the centered conversation.
    <div className="flex w-[56px] shrink-0 flex-col items-center bg-bg py-4">
      <div className="flex size-9 items-center justify-center font-display text-[19px] font-semibold tracking-[-0.03em] text-ink">
        c<span className="text-accent">e</span>
      </div>
      <IconBtn title="Expand sidebar" onClick={toggleSidebar} className="mt-3">
        <SidebarIcon className="size-[18px]" />
      </IconBtn>
      <button
        title="New chat"
        onClick={() => create.mutate()}
        className="mt-3 flex size-[38px] items-center justify-center rounded-[10px] text-muted transition hover:bg-hover hover:text-ink"
      >
        <ComposeIcon className="size-[19px]" />
      </button>
      <div className="flex-1" />
      <Footer collapsed />
    </div>
  )
}

/* ------------------------------------------------------------------- footer */

function Footer({ collapsed = false }: { collapsed?: boolean }) {
  if (collapsed) {
    return (
      <div className="flex flex-col items-center pt-2">
        <SettingsPopover
          align="bottom-[10px] left-[52px]"
          trigger={(toggle) => (
            <button
              title="Local User & settings"
              onClick={toggle}
              className="flex size-[34px] items-center justify-center rounded-full bg-[linear-gradient(135deg,var(--color-accent),#B97A2A)] text-xs font-semibold text-[#1A1408]"
            >
              LU
            </button>
          )}
        />
      </div>
    )
  }

  return (
    <div className="border-t border-line px-2 py-2.5">
      <SettingsPopover
        align="bottom-16 left-0"
        trigger={(toggle) => (
          <button
            onClick={toggle}
            className="flex w-full items-center gap-2.5 rounded-[10px] px-2 py-1.5 transition hover:bg-hover"
            title="Local User & settings"
          >
            <span className="flex size-[30px] shrink-0 items-center justify-center rounded-full bg-[linear-gradient(135deg,var(--color-accent),#B97A2A)] text-[11px] font-semibold text-[#1A1408]">
              LU
            </span>
            <span className="min-w-0 flex-1 text-left leading-tight">
              <span className="block truncate text-[12.5px] font-medium text-ink">Local User</span>
              <span className="block text-[11px] text-faint">Local mode</span>
            </span>
            <SettingsIcon className="size-4 shrink-0 text-faint" />
          </button>
        )}
      />
    </div>
  )
}

/* ------------------------------------------------------- settings + config */

function SettingsPopover({ align, trigger }: { align: string; trigger: (toggle: () => void) => React.ReactNode }) {
  const { data: health } = useHealth()
  const { openHome } = useUI()

  return (
    <Popover className={`${align} w-[320px]`} trigger={({ toggle }) => trigger(toggle)}>
      {(close) => (
        <div className="flex max-h-[76vh] flex-col">
          <div className="flex items-center gap-2.5 border-b border-line px-2.5 pt-1.5 pb-3">
            <span className="flex size-9 items-center justify-center rounded-full bg-[linear-gradient(135deg,var(--color-accent),#B97A2A)] text-xs font-semibold text-[#1A1408]">
              LU
            </span>
            <div className="min-w-0">
              <div className="text-[13.5px] font-semibold text-ink">Local User</div>
              <div className="truncate text-[11.5px] text-muted">Single-user local mode</div>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-1 py-1">
            <SectionLabel>Appearance</SectionLabel>
            <div className="px-1.5 pb-1">
              <ThemeToggle />
            </div>

            <Collapsible label="Documents" count={<DocCount />} defaultOpen={false}>
              <DocumentsPanel />
            </Collapsible>

            <Collapsible label="Connected tools" count={<ToolCount />} defaultOpen={false}>
              <ToolsPanel />
            </Collapsible>

            <SectionLabel>Local configuration</SectionLabel>
            <dl className="space-y-1.5 px-2 pb-1 text-[12px]">
              <ConfigRow label="Model" value={health?.llm.model ?? '—'} ok={health?.llm.ok} />
              <div className="pt-0.5">
                <div className="text-faint">Workspace</div>
                <div
                  className="mt-0.5 truncate rounded-md bg-bg2 px-1.5 py-1 font-mono text-[11px] text-muted"
                  title={health?.workspace}
                >
                  {health?.workspace ?? '—'}
                </div>
              </div>
            </dl>
          </div>

          <div className="border-t border-line p-1">
            <button
              onClick={() => {
                close()
                openHome()
              }}
              className="block w-full rounded-lg px-2 py-2 text-left text-[13px] text-muted transition hover:bg-hover hover:text-ink"
            >
              Back to home
            </button>
          </div>
        </div>
      )}
    </Popover>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="px-2 pt-2.5 pb-1 text-[11px] font-medium tracking-wide text-faint uppercase">{children}</div>
}

function Collapsible({
  label,
  count,
  defaultOpen = false,
  children,
}: {
  label: string
  count?: React.ReactNode
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="mt-1.5">
      <button
        onClick={() => setOpen((o) => !o)}
        className="group flex w-full items-center gap-2 rounded-lg px-2 py-2 transition hover:bg-hover"
      >
        <span className="text-[12px] font-medium tracking-wide text-faint uppercase">{label}</span>
        {count}
        <ChevronIcon className={`ml-auto size-4 text-faint transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="px-1 pb-1">{children}</div>}
    </div>
  )
}

function DocCount() {
  const { data: docs = [] } = useDocuments()
  return docs.length ? <span className="text-[11px] text-faint">{docs.length}</span> : null
}

function ToolCount() {
  const { data: health } = useHealth()
  const n = (health?.mcp ?? []).reduce((a, m) => a + m.tools.length, 0)
  return n ? <span className="text-[11px] text-faint">{n}</span> : null
}

function DocumentsPanel() {
  const { data: docs = [] } = useDocuments()
  const upload = useUploadDocument()
  const qc = useQueryClient()
  const remove = useMutation({
    mutationFn: api.deleteDocument,
    onSettled: () => qc.invalidateQueries({ queryKey: keys.documents }),
  })
  const fileRef = useRef<HTMLInputElement>(null)

  return (
    <div className="px-1">
      <button
        onClick={() => fileRef.current?.click()}
        className="mb-1 flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-line py-2 text-[12.5px] text-muted transition hover:border-faint hover:text-ink"
      >
        + Add a document
      </button>
      <input
        ref={fileRef}
        type="file"
        hidden
        multiple
        accept=".pdf,.docx,.txt,.csv,.md,.markdown,.json"
        onChange={(e) => {
          for (const f of Array.from(e.target.files ?? [])) upload.mutate(f)
          e.target.value = ''
        }}
      />
      {upload.error && <div className="mb-1 text-[11.5px] text-danger">{(upload.error as Error).message}</div>}
      {docs.length === 0 ? (
        <div className="px-1 py-1 text-[11.5px] leading-relaxed text-faint">
          Add PDFs, Word docs, notes or data. Connecter searches them when you ask about your own files.
        </div>
      ) : (
        docs.map((d) => (
          <div key={d.id} className="group flex items-center gap-2 rounded-lg px-1.5 py-1.5 hover:bg-hover">
            <DocIcon className="size-4 shrink-0 text-accent" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12.5px] font-medium text-ink" title={d.path}>{d.filename}</div>
              <div className={`text-[11px] ${d.status === 'failed' ? 'text-danger' : 'text-faint'}`} title={d.error ?? undefined}>
                {d.status === 'ready'
                  ? `${d.chunk_count} chunks${d.page_count ? ` · ${d.page_count} pages` : ''}`
                  : d.status === 'failed'
                    ? `Failed: ${d.error ?? ''}`
                    : `${d.status[0].toUpperCase()}${d.status.slice(1)}…`}
              </div>
            </div>
            <button
              title="Remove from index"
              onClick={() => remove.mutate(d.id)}
              className="text-faint opacity-0 transition group-hover:opacity-100 hover:text-danger"
            >
              <TrashIcon className="size-3.5" />
            </button>
          </div>
        ))
      )}
    </div>
  )
}

function ToolsPanel() {
  const { data: health } = useHealth()
  const [open, setOpen] = useState<string | null>(null)
  if (!health) return null
  const rows = [
    { name: 'Local LLM', ok: health.llm.ok, sub: health.llm.ok ? health.llm.model : 'Start LM Studio', tools: [] as string[] },
    { name: 'Document search', ok: health.qdrant, sub: health.qdrant ? 'Qdrant · hybrid + rerank' : 'Qdrant offline', tools: [] as string[] },
    ...health.mcp.map((m) => ({
      name: CAP_LABELS[m.name] ?? m.name,
      ok: m.status === 'ready',
      sub: m.status === 'ready' ? `${m.tools.length} tools` : (m.error ?? m.status),
      tools: m.tools,
    })),
  ]
  return (
    <div className="px-1">
      {rows.map((r) => {
        const expandable = r.tools.length > 0
        const isOpen = open === r.name
        return (
          <div key={r.name}>
            <button
              disabled={!expandable}
              onClick={() => setOpen(isOpen ? null : r.name)}
              className={`flex w-full items-center gap-2 rounded-lg px-1.5 py-1.5 text-left ${expandable ? 'transition hover:bg-hover' : 'cursor-default'}`}
            >
              <span className={`size-2 shrink-0 rounded-full ${r.ok ? 'bg-approve' : 'bg-danger'}`} />
              <span className="min-w-0 flex-1">
                <span className="block text-[12.5px] font-medium text-ink">{r.name}</span>
                <span className="block truncate text-[11px] text-faint">{r.sub}</span>
              </span>
              {expandable && <ChevronIcon className={`size-3.5 text-faint transition ${isOpen ? 'rotate-180' : ''}`} />}
            </button>
            {isOpen && expandable && (
              <div className="mb-1 ml-4 flex flex-wrap gap-1 px-1.5 pb-1">
                {r.tools.map((t) => (
                  <span key={t} className="rounded-md bg-bg2 px-1.5 py-0.5 font-mono text-[10.5px] text-muted">
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function ConfigRow({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-faint">{label}</span>
      <span className="flex min-w-0 items-center gap-1.5">
        {ok !== undefined && <span className={`size-1.5 shrink-0 rounded-full ${ok ? 'bg-approve' : 'bg-danger'}`} />}
        <span className="truncate text-ink" title={value}>
          {value}
        </span>
      </span>
    </div>
  )
}

function IconBtn({
  title,
  onClick,
  children,
  className = '',
}: {
  title: string
  onClick: () => void
  children: React.ReactNode
  className?: string
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={`flex size-[34px] items-center justify-center rounded-[9px] text-muted transition hover:bg-hover hover:text-ink ${className}`}
    >
      {children}
    </button>
  )
}
