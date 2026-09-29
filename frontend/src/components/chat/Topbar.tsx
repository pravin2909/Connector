import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Conversation } from '../../lib/api'
import { keys, useHealth } from '../../lib/hooks'
import { useUI } from '../../store'
import { CloseIcon, ScreenIcon, SettingsIcon } from '../icons'
import { Popover, PopoverItem } from '../Popover'

const tbBtn =
  'flex size-[34px] items-center justify-center rounded-[9px] border border-line text-muted transition hover:border-faint hover:text-ink'

export function Topbar({ conversation }: { conversation: Conversation | undefined }) {
  const { panelOpen, setPanelOpen, openHome, selectConversation } = useUI()
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
  const remove = useMutation({
    mutationFn: () => api.deleteConversation(conversation!.id),
    onSuccess: () => {
      selectConversation(null)
      qc.invalidateQueries({ queryKey: keys.conversations })
    },
  })

  const title = conversation?.title ?? 'Connecter'
  const llmOk = health?.llm.ok

  return (
    <div className="flex shrink-0 items-center justify-between border-b border-line px-[26px] py-4">
      <div className="flex min-w-0 items-center gap-[11px]">
        <div
          className="flex size-[30px] shrink-0 items-center justify-center rounded-[9px] text-[13px] font-semibold text-[#1A1408]"
          style={{ background: conversation?.color ?? 'var(--color-accent)' }}
        >
          {(title.trim()[0] ?? 'C').toUpperCase()}
        </div>
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
            title={conversation ? 'Double-click to rename' : undefined}
            className="truncate font-display text-sm font-semibold md:text-[15.5px]"
          >
            {title}
          </button>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span
          title={llmOk ? `LLM: ${health?.llm.model}` : 'Local LLM unreachable — start LM Studio'}
          className={`mr-1 hidden items-center gap-1.5 text-xs md:flex ${llmOk ? 'text-faint' : 'text-danger'}`}
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
        <Popover
          className="top-11 right-0"
          trigger={({ toggle }) => (
            <button title="Settings" onClick={toggle} className={tbBtn}>
              <SettingsIcon className="size-4" />
            </button>
          )}
        >
          {(close) => (
            <>
              <div className="px-2 pt-1 pb-2 text-xs text-muted">
                Model: <span className="text-ink">{health?.llm.model ?? '…'}</span>
                <br />
                Workspace: <span className="break-all text-ink">{health?.workspace ?? '…'}</span>
              </div>
              {conversation && (
                <>
                  <PopoverItem onClick={() => { close(); setEditing(true) }}>Rename conversation</PopoverItem>
                  <PopoverItem
                    danger
                    onClick={() => {
                      close()
                      if (confirm(`Delete “${title}” and its history?`)) remove.mutate()
                    }}
                  >
                    Delete conversation
                  </PopoverItem>
                </>
              )}
            </>
          )}
        </Popover>
        <button title="Close" onClick={openHome} className={tbBtn}>
          <CloseIcon className="size-4" />
        </button>
      </div>
    </div>
  )
}
