import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Citation, Message } from '../../lib/api'

export function MessageBubble({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="max-w-[82%] self-end rounded-[15px] rounded-br-[4px] bg-ink px-[17px] py-[13px] text-[14.5px] leading-[1.6] whitespace-pre-wrap text-ink-dark max-md:max-w-full">
        {message.content}
      </div>
    )
  }
  return (
    <div className="max-w-[82%] self-start rounded-[15px] rounded-bl-[4px] border border-line bg-panel px-[17px] py-[13px] text-[14.5px] leading-[1.6] max-md:max-w-full">
      <div className="md">
        <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
      </div>
      {message.citations.length > 0 && <Sources citations={message.citations} />}
    </div>
  )
}

function Sources({ citations }: { citations: Citation[] }) {
  return (
    <div className="mt-3 border-t border-line pt-2.5">
      <div className="mb-1.5 text-xs font-medium text-muted">Sources</div>
      <div className="flex flex-col gap-1.5">
        {citations.map((c) => (
          <details key={c.n} className="group rounded-lg bg-bg2 px-2.5 py-1.5 text-[12.5px]">
            <summary className="flex cursor-pointer list-none items-baseline gap-2">
              <span className="font-mono text-accent">[{c.n}]</span>
              <span className="truncate text-ink">{c.document}</span>
              <span className="ml-auto shrink-0 text-faint">
                {[c.page && `Page ${c.page}`, c.section].filter(Boolean).join(' · ')}
              </span>
            </summary>
            <p className="mt-1.5 whitespace-pre-wrap text-muted">{c.snippet}…</p>
          </details>
        ))}
      </div>
    </div>
  )
}
