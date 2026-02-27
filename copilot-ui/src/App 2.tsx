/**
 * App.tsx — Three-panel Copilot UI shell.
 *
 * Layout: [Session 260px] | [Analysis flex] | [Chat 300px]
 * Each side panel is collapsible to 32px icon strip.
 * Header is fixed 44px at top.
 */

import { useState } from 'react'
import { Header } from './components/layout/Header'
import { SessionView } from './components/session/SessionView'
import { AnalysisDashboard } from './components/analysis/AnalysisDashboard'
import { ChatPanel } from './components/chat/ChatPanel'
import { useAbletonSession } from './hooks/useAbletonSession'

export default function App() {
  const [leftOpen, setLeftOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(true)

  // Mount WebSocket at app level — survives panel collapse/remount
  useAbletonSession()

  return (
    <div className="flex flex-col h-screen bg-push-bg text-push-text overflow-hidden">
      {/* Fixed header */}
      <Header />

      {/* Three-panel body below header */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left panel — Session View */}
        <div
          className="flex-shrink-0 border-r border-push-border overflow-hidden transition-all duration-200"
          style={{ width: leftOpen ? '260px' : '32px' }}
        >
          {leftOpen ? (
            <div className="h-full flex flex-col">
              {/* Panel header */}
              <div className="flex items-center justify-between px-2 py-1 border-b border-push-border">
                <span className="text-[9px] uppercase tracking-[0.08em] text-push-muted">
                  Session
                </span>
                <button
                  onClick={() => setLeftOpen(false)}
                  className="text-push-muted hover:text-push-text text-[10px] leading-none"
                  title="Collapse"
                >
                  ◀
                </button>
              </div>
              <div className="flex-1 overflow-y-auto">
                <SessionView />
              </div>
            </div>
          ) : (
            /* Collapsed strip */
            <div className="h-full flex flex-col items-center pt-2">
              <button
                onClick={() => setLeftOpen(true)}
                className="text-push-muted hover:text-push-orange text-[10px] leading-none"
                title="Expand Session"
              >
                ▶
              </button>
              <span
                className="text-[8px] uppercase tracking-[0.08em] text-push-muted mt-2"
                style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
              >
                Session
              </span>
            </div>
          )}
        </div>

        {/* Center panel — Analysis Dashboard */}
        <div className="flex-1 overflow-y-auto min-w-0">
          <AnalysisDashboard />
        </div>

        {/* Right panel — Chat */}
        <div
          className="flex-shrink-0 border-l border-push-border overflow-hidden transition-all duration-200"
          style={{ width: rightOpen ? '320px' : '32px' }}
        >
          {rightOpen ? (
            <div className="h-full flex flex-col">
              {/* Panel header */}
              <div className="flex items-center justify-between px-2 py-1 border-b border-push-border">
                <span className="text-[9px] uppercase tracking-[0.08em] text-push-muted">
                  Chat
                </span>
                <button
                  onClick={() => setRightOpen(false)}
                  className="text-push-muted hover:text-push-text text-[10px] leading-none"
                  title="Collapse"
                >
                  ▶
                </button>
              </div>
              <div className="flex-1 overflow-hidden">
                <ChatPanel />
              </div>
            </div>
          ) : (
            /* Collapsed strip */
            <div className="h-full flex flex-col items-center pt-2">
              <button
                onClick={() => setRightOpen(true)}
                className="text-push-muted hover:text-push-orange text-[10px] leading-none"
                title="Expand Chat"
              >
                ◀
              </button>
              <span
                className="text-[8px] uppercase tracking-[0.08em] text-push-muted mt-2"
                style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
              >
                Chat
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
