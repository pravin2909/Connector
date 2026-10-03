import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Approval, type Run, type Step } from '../../lib/api'
import { keys } from '../../lib/hooks'
import { useUI } from '../../store'
import { ChevronIcon } from '../icons'

/** Everything the agent did for one user message: activity checklist, approvals, status. */
export function RunBlock({ run }: { run: Run }) {
  const active = run.status === 'running' || run.status === 'pending'
  const lastRunning = run.steps.at(-1)?.status === 'running'

  // Split the activity at each approval step so the card appears where the run paused.
  const segments: ({ type: 'steps'; steps: Step[] } | { type: 'approval'; approval: Approval })[] = []
  const placed = new Set<string>()
  for (const s of run.steps) {
    if (s.kind === 'tool_selected') continue // the panel shows these; the thread keeps it compact
    const approval = s.kind === 'approval' && run.approvals.find((a) => a.id === s.detail?.approval_id)
    if (approval) {
      if (!placed.has(approval.id)) segments.push({ type: 'approval', approval })
      placed.add(approval.id)
      continue
    }
    if (s.kind === 'approval') continue
    const last = segments.at(-1)
    if (last?.type === 'steps') last.steps.push(s)
    else segments.push({ type: 'steps', steps: [s] })
  }
  for (const a of run.approvals) if (!placed.has(a.id)) segments.push({ type: 'approval', approval: a })

  return (
    <>
      {segments.map((seg, i) =>
        seg.type === 'steps' ? (
          <Checklist key={`s${i}`} steps={seg.steps} collapsible={!active} />
        ) : (
          <ApprovalCard key={seg.approval.id} approval={seg.approval} conversationId={run.conversation_id} />
        ),
      )}
      {active && !lastRunning && <Thinking />}
      {run.status === 'failed' && (
        <div className="self-center text-center text-[12.5px] text-danger">Run failed — {run.error ?? 'unknown error'}</div>
      )}
      {run.status === 'cancelled' && <div className="self-center text-[12.5px] text-faint">Run cancelled</div>}
    </>
  )
}

function StepIcon({ status }: { status: Step['status'] }) {
  if (status === 'running') return <span className="inline-block size-3 shrink-0 translate-y-1 animate-spin rounded-full border-2 border-accent border-t-transparent" />
  if (status === 'warning') return <span className="shrink-0 text-accent">⚠</span>
  if (status === 'error') return <span className="shrink-0 text-danger">✕</span>
  return <span className="shrink-0 text-accent">✓</span>
}

function stepMeta(step: Step): string | null {
  const d = step.detail ?? {}
  if (Array.isArray(d.sources) && d.sources.length) return d.sources.join(', ')
  if (typeof d.error === 'string') return d.error
  if (typeof d.latency_ms === 'number') return `${(d.latency_ms / 1000).toFixed(1)}s`
  return null
}

export function Checklist({ steps, collapsible }: { steps: Step[]; collapsible: boolean }) {
  const [expanded, setExpanded] = useState(false)

  // A finished run collapses to a single compact summary bar that expands on click,
  // so the thread stays tidy. A live run shows its steps streaming.
  if (collapsible && !expanded) {
    const status = steps.some((s) => s.status === 'error')
      ? 'error'
      : steps.some((s) => s.status === 'warning')
        ? 'warning'
        : 'done'
    return (
      <button
        onClick={() => setExpanded(true)}
        className="group flex items-center gap-2 self-stretch rounded-[12px] border border-line bg-panel px-3.5 py-2.5 text-[13px] text-muted transition hover:border-faint"
      >
        <StepIcon status={status} />
        <span className="font-medium text-ink">Agent activity</span>
        <span className="text-faint">· {steps.length} step{steps.length !== 1 ? 's' : ''}</span>
        <ChevronIcon className="ml-auto size-4 text-faint transition group-hover:text-ink" />
      </button>
    )
  }

  return (
    <div className="flex flex-col gap-2 self-stretch rounded-[12px] border border-line bg-panel px-3.5 py-3 text-[13px]">
      {collapsible && (
        <button
          onClick={() => setExpanded(false)}
          className="group mb-0.5 flex items-center gap-2 text-left text-muted transition hover:text-ink"
        >
          <span className="font-medium text-ink">Agent activity</span>
          <span className="text-faint">· {steps.length} steps</span>
          <ChevronIcon className="ml-auto size-4 rotate-180 text-faint transition group-hover:text-ink" />
        </button>
      )}
      {steps.map((s) => (
        <div key={s.seq}>
          <div className="flex gap-2 text-muted">
            <StepIcon status={s.status} />
            <span className={`min-w-0 ${s.status === 'running' ? 'text-ink' : ''}`}>
              <b className="font-semibold text-ink">{s.label}</b>
              {stepMeta(s) && <span className="text-faint">&nbsp;→ {stepMeta(s)}</span>}
            </span>
          </div>
          {s.kind === 'plan' && Array.isArray(s.detail?.steps) && (s.detail.steps as string[]).length > 0 && (
            <ol className="mt-1.5 ml-6 list-decimal space-y-0.5 text-[12.5px] text-faint">
              {(s.detail.steps as string[]).map((p, j) => <li key={j}>{p}</li>)}
            </ol>
          )}
        </div>
      ))}
    </div>
  )
}

function Thinking() {
  return (
    <div className="self-start text-sm text-faint" aria-label="Working">
      {[0, 150, 300].map((d) => (
        <span key={d} className="mr-[3px] inline-block size-[5px] animate-blink rounded-full bg-faint" style={{ animationDelay: `${d}ms` }} />
      ))}
    </div>
  )
}

const CARD_TITLE: Record<string, string> = { email: 'Email', file: 'Files', browser: 'Computer', web: 'Web' }

function ApprovalCard({ approval, conversationId }: { approval: Approval; conversationId: string }) {
  const qc = useQueryClient()
  const screenshot = useUI((s) => s.screenshots[approval.run_id])
  const [tookOver, setTookOver] = useState(false)
  const decide = useMutation({
    mutationFn: (decision: 'approve' | 'reject') => api.decide(approval.id, decision),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.conversation(conversationId) }),
  })
  const pending = approval.status === 'pending'
  const handoff = approval.kind === 'handoff'
  const server = approval.action.split('__')[0]

  const badge = pending
    ? { cls: 'text-accent bg-[rgba(232,163,61,.12)]', text: '✳ Action needed' }
    : approval.status === 'approved'
      ? { cls: 'text-approve bg-[rgba(62,132,100,.16)]', text: handoff ? '✓ Done' : '✓ Approved' }
      : { cls: 'text-danger bg-[rgba(212,106,90,.14)]', text: '✕ Rejected' }

  return (
    <>
      <div className="self-stretch rounded-[15px] border border-line bg-panel px-[18px] py-4">
        <div className="mb-2 flex items-center justify-between">
          <b className="text-sm">{CARD_TITLE[server] ?? server}</b>
          <span className={`flex items-center gap-[5px] rounded-full px-2.5 py-1 text-[11.5px] ${badge.cls}`}>{badge.text}</span>
        </div>
        <div className="text-sm text-muted">{handoff ? approval.summary : approval.reason}</div>
        {handoff ? (
          <div className="relative mt-3 h-[140px] overflow-hidden rounded-[10px] screen-gradient">
            {screenshot && <img src={screenshot} alt="Agent browser" className="size-full object-cover object-top" />}
          </div>
        ) : (
          <pre className="mt-3 max-h-64 overflow-auto rounded-[10px] border border-line bg-bg2 px-3.5 py-3 font-sans text-[13px] leading-relaxed whitespace-pre-wrap text-ink">
            {approval.summary}
          </pre>
        )}
        {pending && (
          <div className="mt-3.5 flex gap-2.5">
            {handoff ? (
              <>
                <button onClick={() => setTookOver(true)} className="rounded-full bg-ink px-4 py-[9px] text-[13px] font-medium text-ink-dark">
                  Take over
                </button>
                <button
                  disabled={decide.isPending}
                  onClick={() => decide.mutate('approve')}
                  className="rounded-full bg-panel-strong px-4 py-[9px] text-[13px] font-medium"
                >
                  I'm done
                </button>
              </>
            ) : (
              <>
                <button
                  disabled={decide.isPending}
                  onClick={() => decide.mutate('approve')}
                  className="rounded-full bg-ink px-4 py-[9px] text-[13px] font-medium text-ink-dark disabled:opacity-60"
                >
                  Approve
                </button>
                <button
                  disabled={decide.isPending}
                  onClick={() => decide.mutate('reject')}
                  className="rounded-full bg-panel-strong px-4 py-[9px] text-[13px] font-medium disabled:opacity-60"
                >
                  Reject
                </button>
              </>
            )}
          </div>
        )}
        {decide.error && <div className="mt-2 text-xs text-danger">{(decide.error as Error).message}</div>}
      </div>
      {tookOver && pending && (
        <div className="self-center text-[12.5px] text-faint">
          You've taken over — use the Connecter browser window, then press “I'm done”.
        </div>
      )}
    </>
  )
}
