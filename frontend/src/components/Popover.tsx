import { useEffect, useRef, useState, type ReactNode } from 'react'

/** Click-to-toggle popover matching the design's `.popover`; closes on outside click / Escape. */
export function Popover({
  trigger,
  children,
  className = 'top-14 right-0',
}: {
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode
  children: (close: () => void) => ReactNode
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={ref} className="relative">
      {trigger({ open, toggle: () => setOpen((o) => !o) })}
      {open && (
        <div
          className={`absolute z-[80] w-[230px] rounded-[14px] border border-line bg-elevated p-2.5 shadow-[0_20px_60px_rgba(0,0,0,.28)] ${className}`}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  )
}

export function PopoverItem({ children, onClick, danger }: { children: ReactNode; onClick?: () => void; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`block w-full rounded-lg px-2 py-2.5 text-left text-[13.5px] hover:bg-hover ${danger ? 'text-danger' : 'text-ink'}`}
    >
      {children}
    </button>
  )
}

export function PopoverHead({ title, subtitle, avatar }: { title: string; subtitle: string; avatar: string }) {
  return (
    <div className="mb-1.5 flex items-center gap-2.5 border-b border-line px-1.5 pt-2 pb-3">
      <div className="flex size-[34px] items-center justify-center rounded-full bg-accent text-xs font-semibold text-[#1b1409]">
        {avatar}
      </div>
      <div className="min-w-0">
        <strong className="block truncate text-sm">{title}</strong>
        <span className="block truncate text-xs text-muted">{subtitle}</span>
      </div>
    </div>
  )
}
