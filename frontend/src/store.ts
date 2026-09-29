import { create } from 'zustand'

interface UIState {
  view: 'home' | 'chat'
  conversationId: string | null
  panelOpen: boolean
  /** Latest browser screenshot per run, from `screenshot` SSE events. */
  screenshots: Record<string, string>
  openChat: (conversationId?: string | null) => void
  openHome: () => void
  selectConversation: (id: string | null) => void
  setPanelOpen: (open: boolean) => void
  setScreenshot: (runId: string, url: string) => void
}

export const useUI = create<UIState>((set) => ({
  view: 'home',
  conversationId: null,
  panelOpen: typeof window === 'undefined' || window.innerWidth > 900,
  screenshots: {},
  openChat: (conversationId) =>
    set((s) => ({ view: 'chat', conversationId: conversationId === undefined ? s.conversationId : conversationId })),
  openHome: () => set({ view: 'home' }),
  selectConversation: (id) => set({ conversationId: id }),
  setPanelOpen: (open) => set({ panelOpen: open }),
  setScreenshot: (runId, url) => set((s) => ({ screenshots: { ...s.screenshots, [runId]: url } })),
}))
