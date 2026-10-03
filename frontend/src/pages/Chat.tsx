import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Dock } from '../components/chat/Dock'
import { MessageBubble } from '../components/chat/MessageBubble'
import { Rail } from '../components/chat/Rail'
import { RunBlock } from '../components/chat/RunBlock'
import { SidePanel } from '../components/chat/SidePanel'
import { Topbar } from '../components/chat/Topbar'
import { api, type ConversationDetail } from '../lib/api'
import { keys, useConversation, useConversations, useRunEvents, useUploadDocument } from '../lib/hooks'
import { useUI } from '../store'

const SUGGESTIONS = [
  'According to my project report, what database did I use?',
  'Find the latest news about the Model Context Protocol and summarise it',
  'List the files in my workspace',
  'Read my project report, research the latest MCP architecture, write a comparison to reports/mcp.md and email it to Rahul',
]

export default function Chat() {
  const { conversationId, selectConversation } = useUI()
  const { data: conversations, isSuccess } = useConversations()
  const { data: detail } = useConversation(conversationId)
  const qc = useQueryClient()
  const [notices, setNotices] = useState<string[]>([])
  const [sendError, setSendError] = useState<string | null>(null)
  const upload = useUploadDocument()

  // Open the most recent conversation when entering the workspace.
  useEffect(() => {
    if (isSuccess && !conversationId && conversations.length) selectConversation(conversations[0].id)
  }, [isSuccess, conversationId, conversations, selectConversation])
  useEffect(() => {
    setNotices([])
    setSendError(null)
  }, [conversationId])

  const latestRun = detail?.runs.at(-1)
  const liveRun = latestRun && ['pending', 'running'].includes(latestRun.status) ? latestRun : undefined
  const busy = !!latestRun && ['pending', 'running', 'awaiting_approval'].includes(latestRun.status)
  useRunEvents(conversationId, liveRun?.id ?? null, !!liveRun)

  const send = useMutation({
    mutationFn: async (text: string) => {
      let id = conversationId
      if (!id) {
        id = (await api.createConversation()).id
        selectConversation(id)
      }
      return api.send(id, text)
    },
    onMutate: () => setSendError(null),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: keys.conversation(res.run.conversation_id) })
      qc.invalidateQueries({ queryKey: keys.conversations })
    },
    onError: (e: Error) => setSendError(e.message),
  })

  const cancel = useMutation({
    mutationFn: () => api.cancelRun(latestRun!.id),
    onSettled: () => conversationId && qc.invalidateQueries({ queryKey: keys.conversation(conversationId) }),
  })

  const title = detail?.conversation.title ?? 'Connecter'

  return (
    <section className="h-screen overflow-hidden">
      <div className="flex h-screen">
        <Rail />
        <div className="flex h-screen min-w-0 flex-1 flex-col">
          <Topbar conversation={detail?.conversation} />
          <Thread detail={detail} notices={notices} error={sendError} onSuggestion={(s) => send.mutate(s)} />
          <Dock
            placeholder="Message Connecter…"
            busy={busy}
            disabled={send.isPending}
            onSend={(t) => send.mutate(t)}
            onStop={() => cancel.mutate()}
            onAttach={(f) =>
              upload.mutate(f, {
                onSuccess: (d) => setNotices((n) => [...n, `Added ${d.filename} to your documents — indexing for search`]),
                onError: (e) => setNotices((n) => [...n, `Couldn't add ${f.name}: ${e.message}`]),
              })
            }
          />
        </div>
        <SidePanel title={title} latestRun={latestRun} />
      </div>
    </section>
  )
}

function Thread({
  detail,
  notices,
  error,
  onSuggestion,
}: {
  detail: ConversationDetail | undefined
  notices: string[]
  error: string | null
  onSuggestion: (s: string) => void
}) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const runs = useMemo(() => new Map(detail?.runs.map((r) => [r.id, r]) ?? []), [detail])
  const signature = JSON.stringify([
    detail?.messages.length,
    detail?.runs.map((r) => [r.status, r.steps.length, r.approvals.length]),
    notices.length,
  ])
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [signature])

  const empty = !detail || detail.messages.length === 0

  return (
    <div className="flex-1 overflow-y-auto px-[26px] pt-7 pb-2.5">
      <div className="mx-auto flex max-w-[760px] flex-col gap-4">
        {empty && (
          <div className="mt-[8vh] flex flex-col items-center text-center">
            <h2 className="font-display text-3xl font-semibold tracking-[-0.03em]">
              What should <span className="text-accent">Connecter</span> do?
            </h2>
            <p className="mt-3 max-w-md text-sm text-muted">
              Ask about your documents, research the web, work with files and email, or drive the browser. Anything
              consequential waits for your approval.
            </p>
            <div className="mt-7 grid w-full gap-2.5 sm:grid-cols-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => onSuggestion(s)}
                  className="rounded-[14px] border border-line bg-panel px-4 py-3 text-left text-[13.5px] text-muted transition hover:border-faint hover:text-ink"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {detail?.messages.map((m) => {
          const run = m.role === 'user' && m.agent_run_id ? runs.get(m.agent_run_id) : undefined
          return (
            <div key={m.id} className="contents">
              <MessageBubble message={m} />
              {run && <RunBlock run={run} />}
            </div>
          )
        })}
        {notices.map((n, i) => (
          <div key={i} className="my-0.5 self-center text-[12.5px] text-faint">{n}</div>
        ))}
        {error && <div className="self-center text-[12.5px] text-danger">{error}</div>}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
