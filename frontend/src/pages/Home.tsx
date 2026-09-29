import { useMemo, useState } from 'react'
import { Popover, PopoverItem } from '../components/Popover'
import { ThemeToggle } from '../components/ThemeToggle'
import {
  BrowserIcon,
  DatabaseIcon,
  FolderIcon,
  GlobeIcon,
  MailIcon,
  SearchIcon,
  ShieldIcon,
} from '../components/icons'
import { useUI } from '../store'

/** Icon type shared by capability cards. */
type Icon = (p: { className?: string }) => React.ReactElement

const BrowserIconLocal: Icon = BrowserIcon

const CAPS: { id: string; Icon: Icon; title: string; body: string }[] = [
  {
    id: 'documents',
    Icon: DatabaseIcon,
    title: 'Agentic RAG',
    body: 'Ask about your own PDFs, notes and data. Connecter decides when private knowledge is needed, retrieves the right passages with hybrid search and reranking, and answers with citations you can open.',
  },
  {
    id: 'web',
    Icon: GlobeIcon,
    title: 'Live web',
    body: 'Search the open web, read pages and pull out the parts that matter — so answers reflect what is true today, not just what the model memorised.',
  },
  {
    id: 'files',
    Icon: FolderIcon,
    title: 'Local files',
    body: 'Read, write and organise files in one controlled workspace on your machine. PDFs, Word, spreadsheets, CSV and Markdown — never a byte outside the folder you chose.',
  },
  {
    id: 'email',
    Icon: MailIcon,
    title: 'Email',
    body: 'Find contacts, read threads and draft replies in your voice. Nothing is ever sent until you have seen it and said yes.',
  },
  {
    id: 'browser',
    Icon: BrowserIconLocal,
    title: 'Real browser',
    body: 'When a task needs a real site — a login, a form, a download — Connecter drives an actual browser and shows you its screen while it works.',
  },
  {
    id: 'approvals',
    Icon: ShieldIcon,
    title: 'Human approval',
    body: 'Every consequential step — sending mail, overwriting a file, submitting a form — pauses for a one-tap approval. You stay in control of anything that matters.',
  },
]

const NAV = [
  {
    label: 'Product',
    items: [
      ['product', DatabaseIcon, 'Capabilities', 'Everything Connecter can do'],
      ['agents', BrowserIconLocal, 'How it works', 'Watch a task run step by step'],
    ],
  },
  {
    label: 'Docs',
    items: [
      ['docs', FolderIcon, 'Getting started', 'Run it locally in minutes'],
      ['company', ShieldIcon, 'Local-first', 'Where your data lives'],
    ],
  },
] as const

const roundIcon =
  'flex size-[46px] items-center justify-center rounded-full border border-line text-muted transition hover:border-faint hover:text-ink'

export function Logo({ className = '' }: { className?: string }) {
  return (
    <div className={`font-display text-[25px] font-semibold tracking-[-0.03em] ${className}`}>
      conn<span className="text-accent">e</span>ct<span className="text-accent">e</span>r
    </div>
  )
}

const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })

export default function Home() {
  const openChat = useUI((s) => s.openChat)

  return (
    <section>
      <TopNav onStart={() => openChat()} />

      <main>
        {/* Hero */}
        <section className="mx-auto max-w-[1240px] px-[25px] py-[90px] md:px-12 md:pt-[150px] md:pb-[120px]">
          <div className="mb-[42px] inline-flex items-center gap-2.5 rounded-full border border-line bg-bg2 px-3.5 py-1.5 text-[13px] text-muted">
            <span className="inline-block size-[7px] rounded-full bg-accent" /> Local-first agent runtime
          </div>
          <h1 className="max-w-[950px] font-display text-[46px] leading-[1.02] font-semibold tracking-[-0.045em] md:text-[82px]">
            The heart of
            <br />
            autonomous work
            <br />
            starts with <b className="font-semibold text-accent">Connecter</b>
          </h1>
          <p className="mt-[34px] max-w-[640px] text-[18px] leading-[1.65] text-muted md:text-[19px]">
            One agent that reasons over your private documents, the live web, your files, your email and a real
            browser — planning multi-step tasks and pausing for your approval before it does anything that matters.
            It runs on your machine, on a model you choose.
          </p>
          <div className="mt-9">
            <button
              onClick={() => openChat()}
              className="group inline-flex items-center gap-2 rounded-full bg-ink px-6 py-[14px] text-sm font-medium text-ink-dark transition hover:opacity-90"
            >
              Get Started
              <span className="transition-transform group-hover:translate-x-0.5">→</span>
            </button>
          </div>

          <div className="mt-16 flex flex-wrap items-center gap-x-8 gap-y-3 text-[13px] text-faint">
            {['Runs locally via LM Studio', 'Your files never leave the machine', 'Model-agnostic', 'Open, auditable activity'].map(
              (t) => (
                <span key={t} className="inline-flex items-center gap-2">
                  <span className="inline-block size-1 rounded-full bg-accent-dim" />
                  {t}
                </span>
              ),
            )}
          </div>
        </section>

        {/* Capabilities */}
        <section id="product" className="mx-auto max-w-[1240px] scroll-mt-24 border-t border-line px-[25px] py-[90px] md:px-12">
          <div className="max-w-[560px]">
            <span className="font-mono text-[11px] tracking-[.14em] text-accent">CAPABILITIES</span>
            <h2 className="mt-4 font-display text-[38px] leading-[1.08] tracking-[-0.035em] md:text-[50px]">
              One agent, every tool.
            </h2>
            <p className="mt-[18px] text-base leading-[1.7] text-muted">
              Connecter reaches your tools through the Model Context Protocol, so each capability is an isolated,
              swappable service — and the agent only picks up the ones a task actually needs.
            </p>
          </div>
          <div className="mt-14 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {CAPS.map(({ id, Icon, title, body }) => (
              <div
                key={id}
                id={id}
                className="group scroll-mt-24 rounded-[18px] border border-line bg-bg2 p-6 transition hover:border-faint"
              >
                <div className="flex size-11 items-center justify-center rounded-[13px] border border-line bg-panel text-accent transition group-hover:border-accent-dim">
                  <Icon className="size-[21px]" />
                </div>
                <h3 className="mt-5 font-display text-[20px] font-semibold tracking-[-0.02em]">{title}</h3>
                <p className="mt-2.5 text-[14.5px] leading-[1.65] text-muted">{body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section
          id="agents"
          className="mx-auto grid max-w-[1240px] scroll-mt-24 grid-cols-1 items-center gap-16 border-t border-line px-[25px] py-[100px] md:grid-cols-[.9fr_1.1fr] md:px-12"
        >
          <div>
            <span className="font-mono text-[11px] tracking-[.14em] text-accent">HOW IT WORKS</span>
            <h2 className="mt-4 font-display text-[38px] leading-[1.08] tracking-[-0.035em] md:text-[50px]">
              See the work,
              <br />
              step by step.
            </h2>
            <p className="mt-[18px] max-w-[480px] text-base leading-[1.7] text-muted">
              Connecter understands your goal, plans it, and then thinks in the open: which tool it chose, what it
              found, and where it needs your sign-off. No hidden reasoning — only real, auditable actions.
            </p>
            <ol className="mt-8 space-y-3.5">
              {[
                ['Understand & plan', 'It breaks your goal into concrete steps.'],
                ['Pick the right tool', 'RAG, web, files, email or the browser — only what fits.'],
                ['Act & observe', 'It runs the step and reacts to the result, re-planning if needed.'],
                ['Ask before it counts', 'Consequential actions wait for your approval.'],
              ].map(([t, d], i) => (
                <li key={t} className="flex gap-3.5">
                  <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-line font-mono text-[11px] text-accent">
                    {i + 1}
                  </span>
                  <div>
                    <div className="text-[14.5px] font-medium">{t}</div>
                    <div className="text-[13.5px] text-muted">{d}</div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
          <ShowcaseWindow />
        </section>

        {/* Local-first / trust */}
        <section
          id="company"
          className="mx-auto max-w-[1240px] scroll-mt-24 border-t border-line px-[25px] py-[100px] md:px-12"
        >
          <div className="grid grid-cols-1 gap-14 md:grid-cols-2">
            <div>
              <span className="font-mono text-[11px] tracking-[.14em] text-accent">LOCAL-FIRST</span>
              <h2 className="mt-4 font-display text-[38px] leading-[1.08] tracking-[-0.035em] md:text-[50px]">
                Built around trust.
              </h2>
            </div>
            <p className="max-w-[500px] self-end text-base leading-[1.7] text-muted">
              The model runs on your hardware. Your documents are indexed and searched on your machine. Cloud is used
              only when a task genuinely needs it — reaching the web, or sending mail — and never for your private
              data. Every action the agent takes is visible and reversible-by-design.
            </p>
          </div>
          <div className="mt-14 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              ['On your machine', 'The LLM, your files and the vector index all stay local.'],
              ['You choose the model', 'Point it at any OpenAI-compatible model in LM Studio.'],
              ['Nothing silent', 'Every tool call is logged; consequential ones need a yes.'],
            ].map(([t, d]) => (
              <div key={t} className="rounded-[18px] border border-line bg-bg2 p-6">
                <h3 className="font-display text-[18px] font-semibold tracking-[-0.02em]">{t}</h3>
                <p className="mt-2 text-[14px] leading-[1.6] text-muted">{d}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Docs / CTA band */}
        <section
          id="docs"
          className="mx-auto max-w-[1240px] scroll-mt-24 border-t border-line px-[25px] py-[100px] md:px-12"
        >
          <div className="flex flex-col items-start justify-between gap-8 rounded-[24px] border border-line bg-bg2 p-10 md:flex-row md:items-center md:p-14">
            <div>
              <h2 className="font-display text-[32px] leading-[1.1] tracking-[-0.03em] md:text-[40px]">
                Ready when you are.
              </h2>
              <p className="mt-3 max-w-[440px] text-[15px] leading-[1.65] text-muted">
                Start LM Studio, open the workspace, and hand Connecter your first task. Everything runs on this
                machine.
              </p>
            </div>
            <button
              onClick={() => openChat()}
              className="shrink-0 rounded-full bg-accent px-7 py-[14px] text-sm font-semibold text-[#1b1409] transition hover:opacity-90"
            >
              Open the workspace →
            </button>
          </div>
          <div className="mt-12 flex flex-col items-center gap-2 text-center text-[13px] text-faint">
            <Logo className="!text-[19px] opacity-70" />
            <span>Local-first AI computer agent · runs on your machine</span>
          </div>
        </section>
      </main>
    </section>
  )
}

function TopNav({ onStart }: { onStart: () => void }) {
  return (
    <nav className="sticky top-0 z-30 flex h-[76px] items-center justify-between border-b border-line bg-[color-mix(in_srgb,var(--color-bg)_84%,transparent)] px-5 backdrop-blur-[18px] md:px-[38px]">
      <div className="flex items-center gap-[70px]">
        <Logo />
        <div className="hidden items-center gap-[6px] md:flex">
          {NAV.map((group) => (
            <NavMenu key={group.label} group={group} />
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <SiteSearch />
        <Popover
          className="top-14 right-0 w-[240px]"
          trigger={({ toggle }) => (
            <button className={roundIcon} onClick={toggle} aria-label="Settings">
              <GearGlyph />
            </button>
          )}
        >
          {() => (
            <div className="p-1">
              <div className="px-1 pb-2 text-[11px] font-medium tracking-wide text-faint uppercase">Appearance</div>
              <ThemeToggle />
              <div className="mt-2 border-t border-line pt-2">
                <PopoverItem onClick={onStart}>Open workspace →</PopoverItem>
              </div>
            </div>
          )}
        </Popover>
      </div>
    </nav>
  )
}

function NavMenu({ group }: { group: (typeof NAV)[number] }) {
  return (
    <Popover
      className="top-11 left-0 w-[280px]"
      trigger={({ toggle, open }) => (
        <button
          onClick={toggle}
          className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-[15px] transition hover:bg-bg2 hover:text-ink ${
            open ? 'text-ink' : 'text-muted'
          }`}
        >
          {group.label}
          <i className="inline-block size-1.5 rotate-45 border-r-2 border-b-2 border-current opacity-70" />
        </button>
      )}
    >
      {(close) => (
        <div className="flex flex-col gap-0.5">
          {group.items.map(([id, Icon, title, desc]) => (
            <button
              key={id}
              onClick={() => {
                close()
                scrollTo(id)
              }}
              className="flex items-start gap-3 rounded-[10px] p-2.5 text-left transition hover:bg-hover"
            >
              <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-line bg-bg2 text-accent">
                <Icon className="size-4" />
              </span>
              <span>
                <span className="block text-[13.5px] font-medium text-ink">{title}</span>
                <span className="block text-[12px] text-muted">{desc}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </Popover>
  )
}

/** Working search: filters capabilities & sections, jumps to the match. */
const SEARCH_INDEX = [
  ...CAPS.map((c) => ({ id: c.id, title: c.title, hint: c.body })),
  { id: 'agents', title: 'How it works', hint: 'The agent loop, step by step' },
  { id: 'company', title: 'Local-first', hint: 'Where your data lives' },
  { id: 'docs', title: 'Getting started', hint: 'Run Connecter locally' },
]

function SiteSearch() {
  const [q, setQ] = useState('')
  const results = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) return SEARCH_INDEX
    return SEARCH_INDEX.filter((r) => (r.title + ' ' + r.hint).toLowerCase().includes(t))
  }, [q])

  return (
    <Popover
      className="top-14 right-0 w-[320px]"
      trigger={({ toggle }) => (
        <button className={roundIcon} onClick={toggle} aria-label="Search">
          <SearchIcon className="size-[18px]" />
        </button>
      )}
    >
      {(close) => (
        <div>
          <div className="mb-2 flex items-center gap-2 rounded-lg border border-line bg-bg2 px-2.5 py-2">
            <SearchIcon className="size-4 shrink-0 text-faint" />
            <input
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search Connecter…"
              className="w-full bg-transparent text-[13.5px] text-ink outline-0 placeholder:text-faint"
            />
          </div>
          <div className="max-h-[280px] overflow-y-auto">
            {results.length === 0 ? (
              <div className="px-2 py-3 text-[13px] text-faint">No matches.</div>
            ) : (
              results.map((r) => (
                <button
                  key={r.id}
                  onClick={() => {
                    close()
                    scrollTo(r.id)
                  }}
                  className="block w-full rounded-lg px-2.5 py-2 text-left transition hover:bg-hover"
                >
                  <span className="block text-[13.5px] font-medium text-ink">{r.title}</span>
                  <span className="block truncate text-[12px] text-muted">{r.hint}</span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </Popover>
  )
}

function GearGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="size-[18px]">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" />
    </svg>
  )
}

function ShowcaseWindow() {
  const cards = [
    ['Searching documents', 'Retrieved 4 relevant chunks', 'Done', 'ok'],
    ['Reading project_report.pdf', 'System Architecture · page 12', 'Done', 'ok'],
    ['Drafting email to Rahul', 'Waiting for your approval', 'Approval', 'warn'],
  ] as const
  return (
    <div className="relative overflow-hidden rounded-[22px] border border-line bg-bg2 shadow-[0_30px_90px_rgba(0,0,0,.22)]">
      <div className="flex h-[46px] items-center gap-[7px] border-b border-line px-[18px]">
        {[0, 1, 2].map((i) => (
          <span key={i} className="size-2.5 rounded-full border border-line" />
        ))}
        <span className="ml-3 font-mono text-[11px] text-faint">agent · run</span>
      </div>
      <div className="p-[26px]">
        <div className="mb-4 text-[13px] text-muted">Agent activity</div>
        <div className="flex flex-col gap-2.5">
          {cards.map(([title, sub, tag, kind]) => (
            <div key={title} className="flex items-center gap-3 rounded-[13px] border border-line bg-panel p-[15px]">
              <div className={kind === 'warn' ? 'text-accent' : 'text-approve'}>{kind === 'warn' ? '⚠' : '✓'}</div>
              <div className="min-w-0">
                <strong className="block truncate text-[13px] font-medium">{title}</strong>
                <small className="mt-1 block truncate text-[11.5px] text-faint">{sub}</small>
              </div>
              <em
                className={`ml-auto shrink-0 rounded-full border px-2 py-0.5 text-[10px] not-italic ${
                  kind === 'warn' ? 'border-accent-dim text-accent' : 'border-line text-faint'
                }`}
              >
                {tag}
              </em>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
