import { Popover, PopoverHead, PopoverItem } from '../components/Popover'
import { useUI } from '../store'

const NAV = [
  ['Product', 'products'],
  ['Docs', 'docs'],
  ['Agents', 'agents'],
  ['Company', 'company'],
] as const

const INFO = [
  ['docs', 'DOCS', 'Understand every action.', 'See what the agent is doing, what it used, and where human approval is required.'],
  ['agents', 'AGENTS', 'Tools become actions.', 'Connecter gives agents a controlled way to work across the tools you already use.'],
  ['company', 'COMPANY', 'Built around trust.', 'Local-first execution, visible activity, and human control before anything important happens.'],
] as const

const roundIcon =
  'size-[46px] rounded-full border border-line text-[#aaa39b] transition hover:border-[#555] hover:text-ink'

export function Logo({ className = '' }: { className?: string }) {
  return (
    <div className={`font-display text-[25px] font-semibold tracking-[-0.03em] ${className}`}>
      conn<span className="text-accent">e</span>ct<span className="text-accent">e</span>r
    </div>
  )
}

export default function Home() {
  const openChat = useUI((s) => s.openChat)
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })

  return (
    <section>
      <nav className="sticky top-0 z-30 flex h-[82px] items-center justify-between border-b border-line bg-[rgba(11,11,12,.84)] px-5 backdrop-blur-[18px] md:px-[38px]">
        <Logo />
        <div className="ml-[90px] hidden gap-[42px] md:flex">
          {NAV.map(([label, id]) => (
            <button key={id} onClick={() => scrollTo(id)} className="inline-flex items-center text-[17px] text-[#aaa39b] transition hover:text-ink">
              {label}
              <i className="ml-[7px] inline-block size-1.5 rotate-45 border-r-2 border-b-2 border-current opacity-75" />
            </button>
          ))}
        </div>
        <div className="flex items-center gap-[22px]">
          <Popover trigger={({ toggle }) => <button className={roundIcon} onClick={toggle} aria-label="Search">⌕</button>}>
            {() => (
              <input
                autoFocus
                placeholder="Search Connecter…"
                className="w-full rounded-lg border border-line bg-panel px-2.5 py-2 text-[13.5px] text-ink outline-0"
              />
            )}
          </Popover>
          <Popover trigger={({ toggle }) => <button className={roundIcon} onClick={toggle} aria-label="Settings">⚙</button>}>
            {(close) => (
              <>
                <PopoverItem onClick={close}>Appearance — Dark</PopoverItem>
                <PopoverItem onClick={() => { close(); openChat() }}>Connected tools</PopoverItem>
              </>
            )}
          </Popover>
          <Popover
            trigger={({ toggle }) => (
              <button onClick={toggle} className="flex size-[46px] items-center justify-center rounded-full bg-accent text-[15px] font-semibold text-[#1b1409]">
                LU
              </button>
            )}
          >
            {(close) => (
              <>
                <PopoverHead avatar="LU" title="Local User" subtitle="Running on this machine" />
                <PopoverItem onClick={() => { close(); openChat() }}>Open workspace</PopoverItem>
              </>
            )}
          </Popover>
        </div>
      </nav>

      <main>
        <section className="mx-auto max-w-[1240px] px-[25px] py-[90px] md:px-12 md:pt-[155px] md:pb-[135px]">
          <div className="mb-[46px] text-base text-muted">
            <span className="mr-2.5 inline-block size-[7px] rounded-full bg-accent" /> Local-first agent runtime
          </div>
          <h1 className="max-w-[950px] font-display text-[50px] leading-[1.02] font-semibold tracking-[-0.045em] md:text-[82px]">
            The heart of
            <br />
            autonomous work
            <br />
            starts with <b className="font-semibold text-accent">Connecter</b>
          </h1>
          <p className="mt-[34px] max-w-[680px] text-[19px] leading-[1.65] text-[#a39d96]">
            One agent, every tool. Ask a question, hand off a task, and watch exactly what it does before it does
            anything that matters.
          </p>
          <div className="mt-9 flex gap-3">
            <button onClick={() => openChat()} className="rounded-full bg-ink px-5 py-[13px] text-sm text-ink-dark">
              Get Started <span className="ml-2">→</span>
            </button>
            <button onClick={() => openChat()} className="rounded-full border border-line px-5 py-[13px] text-sm text-muted">
              Hi, Connecter <span className="ml-2">↗</span>
            </button>
          </div>
        </section>

        <section id="products" className="mx-auto grid max-w-[1240px] grid-cols-1 items-center gap-20 px-[25px] pt-20 pb-[150px] md:grid-cols-[.82fr_1.18fr] md:px-12">
          <div>
            <div className="font-mono text-[11px] tracking-[.14em] text-accent">PRODUCT</div>
            <h2 className="mt-[17px] font-display text-[50px] leading-[1.05] tracking-[-0.035em]">
              One place for
              <br />
              your autonomous work.
            </h2>
            <p className="mt-[22px] max-w-[500px] text-base leading-[1.7] text-muted">
              Connecter brings your agents, tools and connected services into one controlled workspace. Ask it to do
              something and see the work happen step by step.
            </p>
            <button onClick={() => openChat()} className="mt-[25px] text-ink">
              Explore Connecter <span className="ml-2">→</span>
            </button>
          </div>
          <ShowcaseWindow />
        </section>

        {INFO.map(([id, kicker, title, body]) => (
          <section key={id} id={id} className="mx-auto grid max-w-[1240px] grid-cols-1 gap-[60px] border-t border-line px-[25px] py-[100px] md:grid-cols-2 md:px-12">
            <div>
              <span className="font-mono text-[11px] tracking-[.14em] text-accent">{kicker}</span>
              <h2 className="mt-[17px] font-display text-[50px] leading-[1.05] tracking-[-0.035em]">{title}</h2>
            </div>
            <p className="max-w-[500px] text-base leading-[1.7] text-muted">{body}</p>
          </section>
        ))}
      </main>
    </section>
  )
}

function ShowcaseWindow() {
  const cards = [
    ['Search documents', 'Retrieved 4 relevant chunks', 'Done'],
    ['Email Rahul', 'Draft ready · waiting for approval', 'Approval'],
  ]
  return (
    <div className="relative h-[440px] overflow-hidden rounded-[22px] border border-line bg-[#161616] shadow-[0_30px_90px_rgba(0,0,0,.35)]">
      <div className="flex h-[45px] items-center gap-[7px] border-b border-line pl-[18px]">
        {[0, 1, 2].map((i) => <span key={i} className="size-2 rounded-full bg-[#3c3c3c]" />)}
      </div>
      <div className="absolute flex w-[120px] flex-col gap-3.5 p-[25px]">
        {[78, 52, 52, 52, 52].map((w, i) => <div key={i} className="h-2 rounded-lg bg-[#292929]" style={{ width: w }} />)}
      </div>
      <div className="ml-[120px] px-[30px] py-[50px]">
        <div className="mb-[22px] text-[15px] text-[#d4d0ca]">Agent activity</div>
        {cards.map(([title, sub, tag]) => (
          <div key={title} className="mb-3 flex items-center gap-[13px] rounded-xl border border-line bg-[#1d1d1d] p-[17px]">
            <div className="text-[#54a98c]">✓</div>
            <div>
              <strong className="block text-[13px]">{title}</strong>
              <small className="mt-[5px] block text-[11px] text-[#777]">{sub}</small>
            </div>
            <em className="ml-auto text-[10px] text-[#777] not-italic">{tag}</em>
          </div>
        ))}
      </div>
    </div>
  )
}
