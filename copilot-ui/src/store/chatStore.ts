import { create } from 'zustand'
import type { ChatMessage } from '../types/chat'

interface ChatStore {
  messages: ChatMessage[]
  pendingInput: string
  isLoading: boolean
  sessionId: string
  addMessage: (message: ChatMessage) => void
  updateMessage: (id: string, patch: Partial<ChatMessage>) => void
  setPendingInput: (input: string) => void
  setLoading: (loading: boolean) => void
  clearHistory: () => void
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  pendingInput: '',
  isLoading: false,
  sessionId: crypto.randomUUID(),

  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  updateMessage: (id, patch) =>
    set((state) => ({
      messages: state.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
    })),

  setPendingInput: (pendingInput) => set({ pendingInput }),
  setLoading: (isLoading) => set({ isLoading }),
  clearHistory: () =>
    set({ messages: [], isLoading: false, pendingInput: '' }),
}))
