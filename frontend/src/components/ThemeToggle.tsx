import { useUI } from '../store'
import { MoonIcon, SunIcon } from './icons'

/** Segmented Dark / Light control bound to the global theme. */
export function ThemeToggle() {
  const theme = useUI((s) => s.theme)
  const setTheme = useUI((s) => s.setTheme)
  const opts = [
    { key: 'dark' as const, label: 'Dark', Icon: MoonIcon },
    { key: 'light' as const, label: 'Light', Icon: SunIcon },
  ]
  return (
    <div className="flex gap-1 rounded-[10px] border border-line bg-bg2 p-1">
      {opts.map(({ key, label, Icon }) => {
        const on = theme === key
        return (
          <button
            key={key}
            onClick={() => setTheme(key)}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-[7px] px-2 py-1.5 text-[12.5px] font-medium transition ${
              on ? 'bg-panel text-ink' : 'text-muted hover:text-ink'
            }`}
          >
            <Icon className="size-3.5" />
            {label}
          </button>
        )
      })}
    </div>
  )
}
