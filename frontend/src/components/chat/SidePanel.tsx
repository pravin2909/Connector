import { type Run } from '../../lib/api'
import { useUI } from '../../store'
import { CloseIcon } from '../icons'
import { Checklist } from './RunBlock'

/** Right-hand panel: the agent's live screen and current run activity.
 *  (Documents and Connected tools now live in the Settings menu.) */
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
            <div className="flex size-full items-end p-3 text-xs text-black/60">No browser activity yet</div>
          )}
        </div>
        <div className="mt-[9px] text-xs text-faint">Live view of the agent's current screen</div>

        {latestRun && latestRun.steps.length > 0 && (
          <div className="mt-[22px]">
            <h4 className="mb-2.5 text-[12.5px] font-medium text-muted">Activity</h4>
            <Checklist steps={latestRun.steps} collapsible={false} />
          </div>
        )}
      </div>
    </aside>
  )
}
