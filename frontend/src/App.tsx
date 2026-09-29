import { useEffect } from 'react'
import Chat from './pages/Chat'
import Home from './pages/Home'
import { useUI } from './store'

export default function App() {
  const view = useUI((s) => s.view)
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [view])
  return view === 'home' ? <Home /> : <Chat />
}
