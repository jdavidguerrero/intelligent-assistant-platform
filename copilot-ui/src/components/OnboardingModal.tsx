/**
 * OnboardingModal — First-run setup modal.
 *
 * Shows once (controlled by `onboardingDone` in workflowStore). Guides the
 * user through verifying services, loading the M4L device, and running a
 * quick end-to-end test.
 *
 * Controlled component: caller decides when to mount/unmount based on
 * `onboardingDone` from workflowStore. Props contain only `onClose`.
 */

import { useEffect, useState } from 'react'
import { useWorkflowStore } from '../store/workflowStore'
import { useSessionStore } from '../store/sessionStore'
import { mcpClient } from '../services/mcpClient'

// ── Types ───────────────────────────────────────────────────────────────────

type CheckState = 'idle' | 'checking' | 'ok' | 'fail'

interface ServiceRow {
  label: string
  state: CheckState
  fix?: string
}

interface TestStep {
  label: string
  state: CheckState
  detail?: string
}

// ── Sub-components ──────────────────────────────────────────────────────────

function StatusIcon({ state }: { state: CheckState }) {
  if (state === 'checking') return <span className="text-[11px] text-push-muted animate-spin inline-block">⟳</span>
  if (state === 'ok') return <span className="text-[11px] text-push-green">✓</span>
  if (state === 'fail') return <span className="text-[11px] text-push-red">✗</span>
  return <span className="text-[11px] text-push-muted">·</span>
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[9px] uppercase tracking-[0.08em] text-push-orange mb-2">{children}</p>
  )
}

function Divider() {
  return <div className="h-px bg-push-border my-4" />
}

// ── Section 1: Service Check ────────────────────────────────────────────────

interface ServiceCheckSectionProps {
  apiState: CheckState
  bridgeState: CheckState
}

function ServiceCheckSection({ apiState, bridgeState }: ServiceCheckSectionProps) {
  const rows: ServiceRow[] = [
    {
      label: 'API (FastAPI)',
      state: apiState,
      fix: 'Run: uvicorn api.main:app --reload --port 8000',
    },
    {
      label: 'Bridge (ALS Listener)',
      state: bridgeState,
      fix: 'Load the ALS Listener M4L device in Ableton',
    },
  ]

  return (
    <div>
      <SectionTitle>1. Verify Services</SectionTitle>
      <div className="flex flex-col gap-2">
        {rows.map((row) => (
          <div key={row.label}>
            <div className="flex items-center gap-2">
              <StatusIcon state={row.state} />
              <span className="text-[11px] text-push-text flex-1">{row.label}</span>
              <span
                className="text-[9px] uppercase tracking-[0.06em]"
                style={{
                  color:
                    row.state === 'ok' ? '#3D8D40' :
                    row.state === 'fail' ? '#E53935' :
                    row.state === 'checking' ? '#B5A020' : '#666',
                }}
              >
                {row.state === 'ok' ? 'OK' :
                 row.state === 'fail' ? 'Not running' :
                 row.state === 'checking' ? 'Checking…' : '—'}
              </span>
            </div>
            {row.state === 'fail' && row.fix && (
              <p className="text-[10px] text-push-muted font-mono mt-1 ml-5 pl-1 border-l border-push-border">
                {row.fix}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Section 2: M4L Device Setup ─────────────────────────────────────────────

function M4LSetupSection() {
  const wsStatus = useSessionStore((s) => s.wsStatus)
  const session = useSessionStore((s) => s.session)

  const steps = [
    'Open Ableton Live',
    'Create a MIDI or audio track',
    'Open Max for Live Device Browser',
    'Navigate to User Library → ALS Listener → ALSListener.amxd',
    'Drag the device onto any track',
    'You\'ll see "ALS Listener: WebSocket server ready" in the Max console',
  ]

  return (
    <div>
      <SectionTitle>2. Load ALS Listener</SectionTitle>

      <ol className="flex flex-col gap-1 mb-3">
        {steps.map((step, i) => (
          <li key={i} className="flex gap-2">
            <span className="text-[9px] text-push-muted flex-shrink-0 w-3 text-right">{i + 1}.</span>
            <span className="text-[10px] text-push-muted leading-snug">{step}</span>
          </li>
        ))}
      </ol>

      {/* Bridge status indicator */}
      {wsStatus === 'connected' && session !== null ? (
        <div className="flex items-center gap-2 mt-1">
          <span className="text-[11px] text-push-green">✓</span>
          <span className="text-[11px] text-push-green">
            Session loaded — {session.tracks.length} tracks
          </span>
        </div>
      ) : wsStatus === 'connected' ? (
        <div className="flex items-center gap-2 mt-1">
          <span className="text-[11px] text-push-green">✓</span>
          <span className="text-[11px] text-push-green">Bridge connected!</span>
        </div>
      ) : (
        <div className="flex items-center gap-2 mt-1">
          <span className="text-[11px] text-push-muted animate-spin inline-block">⟳</span>
          <span className="text-[11px] text-push-muted">Waiting for bridge connection…</span>
        </div>
      )}
    </div>
  )
}

// ── Section 3: Quick Test ───────────────────────────────────────────────────

function QuickTestSection() {
  const wsStatus = useSessionStore((s) => s.wsStatus)
  const [steps, setSteps] = useState<TestStep[]>([
    { label: 'API health check', state: 'idle' },
    { label: 'Bridge connection', state: 'idle' },
    { label: 'Chord generation tool', state: 'idle' },
  ])
  const [running, setRunning] = useState(false)
  const [chordResult, setChordResult] = useState<string | null>(null)

  function patchStep(index: number, patch: Partial<TestStep>) {
    setSteps((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)))
  }

  async function handleTest() {
    setRunning(true)
    setChordResult(null)

    // Reset all steps
    setSteps([
      { label: 'API health check', state: 'idle' },
      { label: 'Bridge connection', state: 'idle' },
      { label: 'Chord generation tool', state: 'idle' },
    ])

    // Step 0 — API health
    patchStep(0, { state: 'checking' })
    try {
      const res = await mcpClient.health()
      patchStep(0, { state: res.status === 'ok' ? 'ok' : 'fail', detail: res.status })
    } catch {
      patchStep(0, { state: 'fail', detail: 'unreachable' })
    }

    // Step 1 — Bridge
    patchStep(1, { state: 'checking' })
    // Small delay so user can see the spinner
    await new Promise((r) => setTimeout(r, 300))
    if (wsStatus === 'connected') {
      patchStep(1, { state: 'ok', detail: 'connected' })
    } else {
      patchStep(1, { state: 'fail', detail: wsStatus })
    }

    // Step 2 — Chord generation
    patchStep(2, { state: 'checking' })
    try {
      const res = await mcpClient.callTool({
        name: 'suggest_chord_progression',
        params: { key: 'A minor', mood: 'melancholic', genre: 'organic house', bars: 4 },
      })
      if (res.success) {
        const raw = res.data
        const chordStr = Array.isArray(raw)
          ? raw.join(' ')
          : typeof raw === 'string'
            ? raw
            : JSON.stringify(raw)
        patchStep(2, { state: 'ok', detail: chordStr })
        setChordResult(chordStr)
      } else {
        patchStep(2, { state: 'fail', detail: res.error ?? 'tool error' })
      }
    } catch (e) {
      patchStep(2, { state: 'fail', detail: e instanceof Error ? e.message : 'error' })
    }

    setRunning(false)
  }

  return (
    <div>
      <SectionTitle>3. Quick Test</SectionTitle>

      <div className="flex flex-col gap-2 mb-3">
        {steps.map((step, i) => (
          <div key={i} className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <StatusIcon state={step.state} />
              <span className="text-[11px] text-push-text">{step.label}</span>
            </div>
            {step.state === 'ok' && step.detail && (
              <p className="text-[9px] font-mono text-push-green ml-5 leading-snug truncate">
                {step.detail}
              </p>
            )}
            {step.state === 'fail' && step.detail && (
              <p className="text-[9px] font-mono text-push-red ml-5 leading-snug truncate">
                {step.detail}
              </p>
            )}
          </div>
        ))}
      </div>

      <button
        onClick={handleTest}
        disabled={running}
        className="px-4 py-1.5 rounded text-[10px] uppercase tracking-[0.06em] border
                   border-push-border text-push-muted
                   hover:border-push-orange hover:text-push-orange
                   disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {running ? 'Testing…' : 'Test Pipeline'}
      </button>

      {chordResult && (
        <p className="text-[10px] font-mono text-push-orange mt-2 leading-relaxed">
          {chordResult}
        </p>
      )}
    </div>
  )
}

// ── Root component ──────────────────────────────────────────────────────────

export interface OnboardingModalProps {
  onClose: () => void
}

export function OnboardingModal({ onClose }: OnboardingModalProps) {
  const setOnboardingDone = useWorkflowStore((s) => s.setOnboardingDone)
  const wsStatus = useSessionStore((s) => s.wsStatus)

  const [apiState, setApiState] = useState<CheckState>('idle')
  const [bridgeState, setBridgeState] = useState<CheckState>('idle')

  // Run health checks on mount
  useEffect(() => {
    let cancelled = false

    async function runChecks() {
      // API check
      setApiState('checking')
      try {
        const res = await fetch('http://localhost:8000/health')
        if (!cancelled) setApiState(res.ok ? 'ok' : 'fail')
      } catch {
        if (!cancelled) setApiState('fail')
      }

      // Bridge is driven by wsStatus from sessionStore — map it
      if (!cancelled) {
        setBridgeState(
          wsStatus === 'connected' ? 'ok' :
          wsStatus === 'connecting' ? 'checking' : 'fail'
        )
      }
    }

    void runChecks()
    return () => { cancelled = true }
  // Run once on mount; also re-evaluate if wsStatus changes while modal is open
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Keep bridgeState in sync with live wsStatus
  useEffect(() => {
    setBridgeState(
      wsStatus === 'connected' ? 'ok' :
      wsStatus === 'connecting' ? 'checking' : 'fail'
    )
  }, [wsStatus])

  const canProceed = apiState === 'ok'

  function handleDone() {
    setOnboardingDone()
    onClose()
  }

  function handleSkip() {
    setOnboardingDone()
    onClose()
  }

  return (
    /* Full-screen overlay */
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      {/* Modal card */}
      <div
        className="bg-push-surface border border-push-border rounded-[6px] w-[480px] max-h-[80vh] overflow-y-auto"
        style={{ maxHeight: '80vh' }}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-push-border">
          <h1 className="text-[14px] font-medium text-push-text leading-snug">
            Welcome to Intelligent Assistant Platform
          </h1>
          <p className="text-[11px] text-push-muted mt-0.5">v1.0</p>
        </div>

        {/* Body */}
        <div className="px-6 py-5">
          <ServiceCheckSection apiState={apiState} bridgeState={bridgeState} />

          <Divider />

          <M4LSetupSection />

          <Divider />

          <QuickTestSection />
        </div>

        {/* Footer */}
        <div className="px-6 pb-6 pt-4 border-t border-push-border flex items-center justify-between">
          <button
            onClick={handleSkip}
            className="text-[10px] text-push-muted hover:text-push-text transition-colors underline underline-offset-2"
          >
            Skip for now
          </button>

          <button
            onClick={handleDone}
            disabled={!canProceed}
            className="px-5 py-2 rounded text-[11px] uppercase tracking-[0.06em] font-medium
                       bg-push-orange text-push-bg
                       hover:brightness-110
                       disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            Get Started →
          </button>
        </div>
      </div>
    </div>
  )
}
