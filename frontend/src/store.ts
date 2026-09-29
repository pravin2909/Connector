import { create } from 'zustand'

export type Theme = 'dark' | 'light'

/** Read the theme the no-flash script in index.html already applied to <html>. */
function initialTheme(): Theme {
  if (typeof document !== 'undefined' && document.documentElement.dataset.theme === 'light') return 'light'
  return 'dark'
}

function applyTheme(theme: Theme) {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.theme = theme
  try {
    localStorage.setItem('connecter-theme', theme)
  } catch {
    /* private mode / storage blocked — the in-memory value still works */
  }
}

interface UIState {
  view: 'home' | 'chat'
  conversationId: string | null
  panelOpen: boolean
  sidebarExpanded: boolean
  theme: Theme
  /** Latest browser screenshot per run, from `screenshot` SSE events. */
  screenshots: Record<string, string>
  openChat: (conversationId?: string | null) => void
  openHome: () => void
  selectConversation: (id: string | null) => void
  setPanelOpen: (open: boolean) => void
  toggleSidebar: () => void
  setSidebarExpanded: (open: boolean) => void
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  setScreenshot: (runId: string, url: string) => void
}

const wide = typeof window === 'undefined' || window.innerWidth > 900

export const useUI = create<UIState>((set) => ({
  view: 'home',
  conversationId: null,
  panelOpen: wide,
  sidebarExpanded: wide,
  theme: initialTheme(),
  screenshots: {},
  openChat: (conversationId) =>
    set((s) => ({ view: 'chat', conversationId: conversationId === undefined ? s.conversationId : conversationId })),
  openHome: () => set({ view: 'home' }),
  selectConversation: (id) => set({ conversationId: id }),
  setPanelOpen: (open) => set({ panelOpen: open }),
  toggleSidebar: () => set((s) => ({ sidebarExpanded: !s.sidebarExpanded })),
  setSidebarExpanded: (open) => set({ sidebarExpanded: open }),
  setTheme: (theme) => {
    applyTheme(theme)
    set({ theme })
  },
  toggleTheme: () =>
    set((s) => {
      const theme: Theme = s.theme === 'dark' ? 'light' : 'dark'
      applyTheme(theme)
      return { theme }
    }),
  setScreenshot: (runId, url) => set((s) => ({ screenshots: { ...s.screenshots, [runId]: url } })),
}))
