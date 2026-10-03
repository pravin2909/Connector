import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Conversation } from '../../lib/api'
import { keys, useHealth } from '../../lib/hooks'
import { useUI } from '../../store'
import { EditIcon, ScreenIcon } from '../icons'

const tbBtn =
  'flex size-[34px] items-center justify-center rounded-[9px] border border-line text-muted transition hover:border-faint hover:text-ink'

export function Topbar({ conversation }: { conversation: Conversation | undefined }) {
  const { panelOpen, setPanelOpen } = useUI()
  const { data: health } = useHealth()
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)

  const rename = useMutation({
    mutationFn: (title: string) => api.renameConversation(conversation!.id, title),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.conversations })
      qc.invalidateQueries({ queryKey: keys.conversation(conversation!.id) })
    },
  })

  const title = conversation?.title ?? 'Connecter'
  const llmOk = health?.llm.ok

  return (
    <div className="flex shrink-0 items-center justify-between border-b border-line px-[18px] py-3.5 md:px-[22px]">
      <div className="flex min-w-0 items-center gap-1.5">
        {editing && conversation ? (
          <input
            autoFocus
            defaultValue={title}
            onBlur={(e) => {
              setEditing(false)
              const v = e.target.value.trim()
              if (v && v !== title) rename.mutate(v)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') e.currentTarget.blur()
              if (e.key === 'Escape') setEditing(false)
            }}
            className="rounded-md border border-line bg-panel px-2 py-0.5 font-display text-[15.5px] font-semibold outline-none"
          />
        ) : (
          <button
            onDoubleClick={() => conversation && setEditing(true)}
            className="group flex min-w-0 items-center gap-2"
            title={conversation ? 'Double-click to rename' : undefined}
          >
            <span className="truncate font-display text-sm font-semibold md:text-[15.5px]">{title}</span>
            {conversation && (
              <EditIcon
                onClick={(e) => {
                  e.stopPropagation()
                  setEditing(true)
                }}
                className="size-3.5 shrink-0 text-faint opacity-0 transition group-hover:opacity-100 hover:text-ink"
              />
            )}
          </button>
        )}
      </div>
      <div className="flex items-center gap-2.5">
        <span
          title={llmOk ? `LLM: ${health?.llm.model}` : 'Local LLM unreachable — start LM Studio'}
          className={`mr-0.5 hidden items-center gap-1.5 text-xs md:flex ${llmOk ? 'text-faint' : 'text-danger'}`}
        >
          <span className={`size-1.5 rounded-full ${llmOk ? 'bg-approve' : 'bg-danger'}`} />
          {llmOk ? health?.llm.model : 'LLM offline'}
        </span>
        <button
          title="Agent screen & activity"
          onClick={() => setPanelOpen(!panelOpen)}
          className={`${tbBtn} ${panelOpen ? 'border-accent-dim bg-[rgba(232,163,61,.1)] !text-accent' : ''}`}
        >
          <ScreenIcon className="size-4" />
        </button>
      </div>
    </div>
  )
}
