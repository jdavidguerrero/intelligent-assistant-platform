/**
 * ChatPanel — Message list + quick actions + textarea input.
 *
 * - Enter = send, Shift+Enter = newline
 * - Listens for 'copilot:focus-chat' event from FIX buttons
 * - QUICK_ACTIONS chips for common queries
 */

import { useEffect, useRef } from 'react'
import { useCopilotChat } from '../../hooks/useCopilotChat'
import { ChatMessage } from './ChatMessage'
import { ActionCard } from './ActionCard'
import { QUICK_ACTIONS } from '../../types/chat'

export function ChatPanel() {
  const { messages, isLoading, pendingInput, send, setPendingInput, clearHistory } = useCopilotChat()
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Listen for focus-chat event from FIX buttons
  useEffect(() => {
    function onFocusChat() {
      textareaRef.current?.focus()
    }
    window.addEventListener('copilot:focus-chat', onFocusChat)
    return () => window.removeEventListener('copilot:focus-chat', onFocusChat)
  }, [])

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleSend() {
    const query = pendingInput.trim()
    if (!query || isLoading) return
    send(query)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages list */}
      <div className="flex-1 overflow-y-auto py-2 space-y-0.5">
        {messages.length === 0 && (
          <div className="px-4 py-8 text-center">
            <div className="text-[10px] text-push-muted">
              Ask anything about your mix
            </div>
            <div className="text-[9px] text-push-muted opacity-60 mt-1">
              Use FIX buttons on detected problems to get specific advice
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Quick actions */}
      <div className="px-3 py-2 border-t border-push-border">
        <div className="flex flex-wrap gap-1">
          {QUICK_ACTIONS.map((action) => (
            <ActionCard
              key={action.id}
              action={action}
              onClick={(q) => send(q)}
              disabled={isLoading}
            />
          ))}
          {messages.length > 0 && (
            <button
              onClick={clearHistory}
              className="
                px-2 py-1 rounded-[3px] border text-[9px] uppercase tracking-[0.08em]
                border-push-border text-push-muted
                hover:border-push-red hover:text-push-red
                transition-colors duration-100
                whitespace-nowrap ml-auto
              "
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Input area */}
      <div className="px-3 pb-3 pt-1 border-t border-push-border">
        <div className="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            value={pendingInput}
            onChange={(e) => setPendingInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your mix… (Enter to send)"
            disabled={isLoading}
            rows={2}
            className="
              flex-1 bg-push-surface border border-push-border rounded-[3px]
              px-2 py-1.5 text-[11px] text-push-text
              placeholder-push-muted resize-none
              focus:outline-none focus:border-push-orange
              disabled:opacity-50
            "
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !pendingInput.trim()}
            className="
              px-2 py-1 rounded-[3px] border text-[10px]
              border-push-orange text-push-orange
              hover:bg-push-orange hover:text-push-bg
              disabled:opacity-40 disabled:cursor-not-allowed
              transition-colors duration-100
              self-end
            "
          >
            {isLoading ? '…' : '↑'}
          </button>
        </div>
        <div className="text-[8px] text-push-muted mt-1 opacity-60">
          Shift+Enter for newline
        </div>
      </div>
    </div>
  )
}
