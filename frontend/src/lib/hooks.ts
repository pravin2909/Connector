import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useUI } from '../store'
import { api, type ConversationDetail, type Step } from './api'

export const keys = {
  conversations: ['conversations'] as const,
  conversation: (id: string) => ['conversation', id] as const,
  documents: ['documents'] as const,
  health: ['health'] as const,
  tools: ['tools'] as const,
}

export function useConversations() {
  return useQuery({ queryKey: keys.conversations, queryFn: api.conversations })
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: keys.conversation(id ?? ''),
    queryFn: () => api.conversation(id!),
    enabled: !!id,
  })
}

export function useDocuments() {
  return useQuery({
    queryKey: keys.documents,
    queryFn: api.documents,
    // Poll while anything is still being indexed.
    refetchInterval: (q) => (q.state.data?.some((d) => d.status === 'queued' || d.status === 'processing') ? 1500 : false),
  })
}

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: api.health, refetchInterval: 20_000 })
}

export function useTools() {
  return useQuery({ queryKey: keys.tools, queryFn: api.tools, refetchInterval: 30_000 })
}

export function useUploadDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.uploadDocument,
    onSettled: () => qc.invalidateQueries({ queryKey: keys.documents }),
  })
}

/**
 * Subscribes to a run's Server-Sent Events while it is running and folds them into the
 * cached conversation, so the thread and activity panel update live.
 */
export function useRunEvents(conversationId: string | null, runId: string | null, running: boolean) {
  const qc = useQueryClient()
  const setScreenshot = useUI((s) => s.setScreenshot)

  useEffect(() => {
    if (!conversationId || !runId || !running) return
    const key = keys.conversation(conversationId)
    const es = new EventSource(`/api/runs/${runId}/events`)

    const patchRun = (fn: (steps: Step[]) => Step[]) =>
      qc.setQueryData<ConversationDetail>(key, (d) =>
        d && { ...d, runs: d.runs.map((r) => (r.id === runId ? { ...r, steps: fn(r.steps) } : r)) },
      )
    const refresh = () => {
      qc.invalidateQueries({ queryKey: key })
      qc.invalidateQueries({ queryKey: keys.conversations })
    }

    es.addEventListener('step', (e) => {
      const { step } = JSON.parse((e as MessageEvent).data) as { step: Step }
      patchRun((steps) => {
        const i = steps.findIndex((s) => s.seq === step.seq)
        if (i === -1) return [...steps, step]
        const next = [...steps]
        next[i] = { ...next[i], ...step, detail: { ...(next[i].detail ?? {}), ...(step.detail ?? {}) } }
        return next
      })
    })
    es.addEventListener('screenshot', (e) => {
      const { url } = JSON.parse((e as MessageEvent).data) as { url: string }
      setScreenshot(runId, url)
    })
    for (const type of ['approval_required', 'message', 'error']) es.addEventListener(type, refresh)
    es.addEventListener('done', () => {
      es.close()
      refresh()
    })
    return () => es.close()
  }, [conversationId, runId, running, qc, setScreenshot])
}
