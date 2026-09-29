import { useEffect, useRef, useState } from 'react'
import { MicIcon, SendIcon, StopIcon } from '../icons'

// Minimal typing for the (prefixed) Web Speech API.
type Recognition = {
  continuous: boolean
  interimResults: boolean
  onresult: (e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void
  onend: () => void
  start: () => void
  stop: () => void
}
const SpeechRecognition: (new () => Recognition) | undefined =
  (window as unknown as Record<string, new () => Recognition>).SpeechRecognition ??
  (window as unknown as Record<string, new () => Recognition>).webkitSpeechRecognition

export function Dock({
  placeholder,
  busy,
  disabled,
  onSend,
  onStop,
  onAttach,
}: {
  placeholder: string
  busy: boolean
  disabled?: boolean
  onSend: (text: string) => void
  onStop: () => void
  onAttach: (file: File) => void
}) {
  const [text, setText] = useState('')
  const [recording, setRecording] = useState(false)
  const recRef = useRef<Recognition | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => () => recRef.current?.stop(), [])

  const submit = () => {
    const t = text.trim()
    if (!t || busy || disabled) return
    onSend(t)
    setText('')
  }

  const toggleMic = () => {
    if (!SpeechRecognition) {
      alert('Voice input is not supported in this browser (try Chrome or Safari).')
      return
    }
    if (recording) {
      recRef.current?.stop()
      return
    }
    const rec = new SpeechRecognition()
    rec.continuous = false
    rec.interimResults = true
    const prefix = text ? text + ' ' : ''
    rec.onresult = (e) => setText(prefix + Array.from(e.results).map((r) => r[0].transcript).join(''))
    rec.onend = () => setRecording(false)
    recRef.current = rec
    rec.start()
    setRecording(true)
    inputRef.current?.focus()
  }

  const action = busy ? 'stop' : text.trim() ? 'send' : 'mic'

  return (
    <div className="shrink-0 px-[26px] pt-3.5 pb-[22px]">
      <div className="mx-auto flex max-w-[760px] items-center gap-3 rounded-full border border-line bg-panel py-[9px] pr-[9px] pl-2 focus-within:border-accent-dim">
        <button
          title="Add a document for Connecter to read"
          onClick={() => fileRef.current?.click()}
          className="flex size-8 shrink-0 items-center justify-center rounded-full bg-panel-strong text-base text-muted transition hover:text-ink"
        >
          +
        </button>
        <input
          ref={fileRef}
          type="file"
          hidden
          accept=".pdf,.docx,.txt,.csv,.md,.markdown,.json"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) onAttach(f)
            e.target.value = ''
          }}
        />
        <input
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.nativeEvent.isComposing && submit()}
          placeholder={recording ? 'Listening…' : placeholder}
          disabled={disabled}
          className="min-w-0 flex-1 bg-transparent text-[14.5px] text-ink outline-none placeholder:text-faint"
        />
        <button
          title={action === 'stop' ? 'Stop run' : action === 'send' ? 'Send' : 'Voice input'}
          onClick={action === 'stop' ? onStop : action === 'send' ? submit : toggleMic}
          className={`flex size-9 shrink-0 items-center justify-center rounded-full text-ink-dark transition ${
            recording ? 'bg-accent' : 'bg-ink'
          }`}
        >
          {action === 'stop' ? <StopIcon className="size-3.5" /> : action === 'send' ? <SendIcon className="size-[15px]" /> : <MicIcon className="size-[15px]" />}
        </button>
      </div>
    </div>
  )
}
