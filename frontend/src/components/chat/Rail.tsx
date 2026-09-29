import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { keys, useConversations } from '../../lib/hooks'
import { useUI } from '../../store'
import { HomeIcon } from '../icons'
import { Popover, PopoverHead, PopoverItem } from '../Popover'

export function Rail() {
  const { data: conversations = [] } = useConversations()
  const { conversationId, selectConversation, openHome } = useUI()
  const qc = useQueryClient()
  const create = useMutation({
    mutationFn: api.createConversation,
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: keys.conversations })
      selectConversation(c.id)
    },
  })

  return (
    <div className="flex w-14 shrink-0 flex-col items-center border-r border-line bg-bg2 py-4 md:w-[68px]">
      <button
        title="New chat"
        onClick={() => create.mutate()}
        className="mb-4 flex size-[38px] shrink-0 items-center justify-center rounded-xl border border-dashed border-line text-lg text-faint transition hover:border-faint hover:text-ink"
      >
        +
      </button>
      <div className="flex w-full flex-1 flex-col items-center gap-2.5 overflow-y-auto py-1">
        {conversations.map((c) => {
          const active = c.id === conversationId
          return (
            <button
              key={c.id}
              title={c.title}
              onClick={() => selectConversation(c.id)}
              style={{ background: c.color }}
              className={`flex size-10 shrink-0 items-center justify-center text-sm font-semibold text-[#14110C] transition-[opacity,border-radius] ${
                active
                  ? 'rounded-[14px] opacity-100 shadow-[0_0_0_2px_var(--color-bg2),0_0_0_3.5px_var(--color-accent-dim)]'
                  : 'rounded-xl opacity-55 hover:opacity-85'
              }`}
            >
              {(c.title.trim()[0] ?? 'N').toUpperCase()}
            </button>
          )
        })}
      </div>
      <div className="flex flex-col items-center gap-3.5 pt-3.5">
        <button
          title="Home"
          onClick={openHome}
          className="flex size-[38px] items-center justify-center rounded-[10px] text-muted transition hover:bg-panel hover:text-ink"
        >
          <HomeIcon className="size-[19px]" />
        </button>
        <Popover
          className="bottom-[52px] -left-1.5 w-[210px]"
          trigger={({ toggle }) => (
            <button
              title="Account"
              onClick={toggle}
              className="flex size-[34px] items-center justify-center rounded-full bg-[linear-gradient(135deg,var(--color-accent),#B97A2A)] text-xs font-semibold text-[#1A1408]"
            >
              LU
            </button>
          )}
        >
          {(close) => (
            <>
              <PopoverHead avatar="LU" title="Local User" subtitle="Single-user local mode" />
              <PopoverItem onClick={() => { close(); openHome() }}>Back to home</PopoverItem>
            </>
          )}
        </Popover>
      </div>
    </div>
  )
}
