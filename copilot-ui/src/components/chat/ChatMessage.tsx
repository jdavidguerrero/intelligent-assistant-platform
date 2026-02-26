/**
 * ChatMessage — Single message bubble.
 *
 * User: right-aligned dark bubble.
 * Assistant: left-aligned with orange left border, optional streaming cursor.
 */

import { Badge } from '../common/Badge'
import type { ChatMessage as ChatMessageType } from '../../types/chat'

interface Props {
  message: ChatMessageType
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end px-3 py-1">
        <div className="
          max-w-[85%] px-3 py-2 rounded-[3px]
          bg-[#222222] text-push-text text-[11px] leading-relaxed
        ">
          {message.content}
        </div>
      </div>
    )
  }

  // Assistant message
  return (
    <div className="flex flex-col px-3 py-1 gap-1">
      <div className="
        max-w-full px-3 py-2 rounded-[3px]
        bg-push-surface border-l-2 text-push-text text-[11px] leading-relaxed
        whitespace-pre-wrap
      " style={{ borderLeftColor: '#FF7700' }}>
        {message.content}
        {message.isStreaming && (
          <span className="animate-pulse ml-0.5 text-push-orange">▎</span>
        )}
        {message.error && (
          <div className="mt-1 text-[10px] text-push-red">
            Error: {message.error}
          </div>
        )}
      </div>

      {/* Footer: mode badge + sources */}
      {!message.isStreaming && (
        <div className="flex flex-wrap items-center gap-1 px-1">
          {message.mode && (
            <Badge variant="status" value={message.mode} />
          )}
          {message.citations && message.citations.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {message.citations.map((c) => (
                <span
                  key={c}
                  className="px-1.5 py-0.5 rounded-[2px] bg-push-elevated text-[9px] text-push-muted font-mono"
                >
                  [{c}]
                </span>
              ))}
            </div>
          )}
          {message.usage?.total_tokens && (
            <span className="text-[9px] text-push-muted font-mono ml-auto">
              {message.usage.total_tokens}t
            </span>
          )}
        </div>
      )}
    </div>
  )
}
