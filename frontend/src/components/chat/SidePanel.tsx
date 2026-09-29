import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { api, type Run } from '../../lib/api'
import { keys, useDocuments, useHealth, useUploadDocument } from '../../lib/hooks'
import { useUI } from '../../store'
import { CloseIcon, DocIcon, TrashIcon } from '../icons'
import { Checklist } from './RunBlock'

const CAP_LABELS: Record<string, string> = {
  file: 'Files (workspace)',
  web: 'Web',
  email: 'Email',
  browser: 'Browser',
}

/** Right-hand panel: the agent's live screen, current run activity, documents and tools. */
export function SidePanel({ title, latestRun }: { title: string; latestRun: Run | undefined }) {
  const { panelOpen, setPanelOpen, screenshots } = useUI()
  const screenshot = latestRun ? screenshots[latestRun.id] : undefined

  return (
    <aside
      className={`shrink-0 overflow-hidden bg-bg2 transition-[width,border-color] duration-200 max-[900px]:fixed max-[900px]:top-0 max-[900px]:right-0 max-[900px]:z-60 max-[900px]:h-screen ${
        panelOpen
          ? 'w-[320px] border-l border-line max-[900px]:shadow-[-20px_0_40px_rgba(0,0,0,.4)]'
          : 'w-0 border-l border-transparent'
      }`}
    >
      <div className="h-screen w-[320px] overflow-y-auto p-[18px]">
        <div className="mb-3.5 flex items-center justify-between">
          <span className="truncate text-[13px] text-muted">{title}'s screen</span>
          <button
            title="Close"
            onClick={() => setPanelOpen(false)}
            className="flex size-[26px] items-center justify-center rounded-[7px] text-faint hover:bg-panel hover:text-ink"
          >
            <CloseIcon className="size-3.5" />
          </button>
        </div>

        <div className="relative h-[180px] overflow-hidden rounded-[14px] screen-gradient">
          {screenshot ? (
            <a href={screenshot} target="_blank" rel="noreferrer">
              <img src={screenshot} alt="Agent's browser" className="size-full object-cover object-top" />
            </a>
          ) : (
            <div className="flex size-full items-end p-3 text-xs text-[#1b1b1b]/70">No browser activity yet</div>
          )}
        </div>
        <div className="mt-[9px] text-xs text-faint">Live view of the agent's current screen</div>

        {latestRun && latestRun.steps.length > 0 && (
          <Section title="Activity">
            <Checklist steps={latestRun.steps} collapsible={false} />
          </Section>
        )}
        <DocumentsSection />
        <ToolsSection />
      </div>
    </aside>
  )
}

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="mt-[22px]">
      <div className="mb-2.5 flex items-center justify-between">
        <h4 className="text-[12.5px] font-medium text-muted">{title}</h4>
        {action}
      </div>
      {children}
    </div>
  )
}

function DocumentsSection() {
  const { data: docs = [] } = useDocuments()
  const upload = useUploadDocument()
  const qc = useQueryClient()
  const remove = useMutation({
    mutationFn: api.deleteDocument,
    onSettled: () => qc.invalidateQueries({ queryKey: keys.documents }),
  })
  const fileRef = useRef<HTMLInputElement>(null)

  return (
    <Section
      title="Documents"
      action={
        <>
          <button onClick={() => fileRef.current?.click()} className="text-xs text-accent hover:underline">
            + Add
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
        </>
      }
    >
      {upload.error && <div className="mb-2 text-xs text-danger">{(upload.error as Error).message}</div>}
      {docs.length === 0 ? (
        <div className="text-xs leading-relaxed text-faint">
          Add PDFs, Word docs, notes or data files. Connecter searches them when you ask about your own documents.
        </div>
      ) : (
        docs.map((d) => (
          <div key={d.id} className="group flex items-center gap-2.5 border-t border-line py-2.5">
            <DocIcon className="size-4 shrink-0 text-accent" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13.5px] font-medium" title={d.path}>{d.filename}</div>
              <div className={`text-[11.5px] ${d.status === 'failed' ? 'text-danger' : 'text-faint'}`} title={d.error ?? undefined}>
                {d.status === 'ready'
                  ? `${d.chunk_count} chunks${d.page_count ? ` · ${d.page_count} pages` : ''}`
                  : d.status === 'failed'
                    ? `Failed: ${d.error ?? ''}`
                    : `${d.status[0].toUpperCase()}${d.status.slice(1)}…`}
              </div>
            </div>
            <button
              title="Remove from index (file stays in workspace)"
              onClick={() => remove.mutate(d.id)}
              className="text-faint opacity-0 transition group-hover:opacity-100 hover:text-danger"
            >
              <TrashIcon className="size-3.5" />
            </button>
          </div>
        ))
      )}
    </Section>
  )
}

function ToolsSection() {
  const { data: health } = useHealth()
  if (!health) return null
  const rows = [
    { name: 'Local LLM', ok: health.llm.ok, sub: health.llm.ok ? health.llm.model : 'Start LM Studio server' },
    { name: 'Document search', ok: health.qdrant, sub: health.qdrant ? 'Qdrant · hybrid + rerank' : 'Qdrant unreachable' },
    ...health.mcp.map((m) => ({
      name: CAP_LABELS[m.name] ?? m.name,
      ok: m.status === 'ready',
      sub: m.status === 'ready' ? `${m.tools.length} tools` : (m.error ?? m.status),
    })),
  ]
  return (
    <Section title="Connected tools">
      {rows.map((r) => (
        <div key={r.name} className="flex items-center gap-2.5 border-t border-line py-2.5">
          <span className={`size-2 shrink-0 rounded-full ${r.ok ? 'bg-approve' : 'bg-danger'}`} />
          <div className="min-w-0">
            <div className="text-[13.5px] font-medium">{r.name}</div>
            <div className="truncate text-[11.5px] text-faint">{r.sub}</div>
          </div>
        </div>
      ))}
    </Section>
  )
}
