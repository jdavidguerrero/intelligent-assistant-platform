import { useChatStore } from '../store/chatStore'
import { mcpClient, McpError } from '../services/mcpClient'
import type { ChatMessage } from '../types/chat'

export function useCopilotChat() {
  const { messages, isLoading, pendingInput, sessionId,
    addMessage, updateMessage, setPendingInput, setLoading, clearHistory } = useChatStore()

  async function send(query: string) {
    if (!query.trim() || isLoading) return
    setLoading(true)
    setPendingInput('')

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: query,
      timestamp: Date.now(),
    }
    addMessage(userMsg)

    const assistantId = crypto.randomUUID()
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      isStreaming: true,
    }
    addMessage(assistantMsg)

    try {
      const stream = mcpClient.askStream({
        query,
        session_id: sessionId,
        use_tools: true,
      })

      let content = ''
      for await (const event of stream) {
        if (event.type === 'chunk') {
          content += event.content
          updateMessage(assistantId, { content })
        } else if (event.type === 'done') {
          updateMessage(assistantId, {
            content,
            isStreaming: false,
            citations: event.citations,
            usage: event.usage as ChatMessage['usage'],
          })
        } else if (event.type === 'sources') {
          updateMessage(assistantId, {
            sources: event.sources as ChatMessage['sources'],
          })
        } else if (event.type === 'error') {
          updateMessage(assistantId, {
            content: content || '(no response)',
            isStreaming: false,
            error: event.message,
          })
        }
      }
      // Ensure streaming is marked done even if no 'done' event
      updateMessage(assistantId, { isStreaming: false })
    } catch (err) {
      const msg = err instanceof McpError
        ? err.detail
        : err instanceof Error ? err.message : 'Request failed'
      updateMessage(assistantId, {
        content: '',
        isStreaming: false,
        error: msg,
      })
    } finally {
      setLoading(false)
    }
  }

  return {
    messages,
    isLoading,
    pendingInput,
    send,
    setPendingInput,
    clearHistory,
  }
}
