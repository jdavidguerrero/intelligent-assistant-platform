/**
 * WorkflowShell — reusable step-machine wrapper for all 5 workflows.
 *
 * Renders:
 *   - Step progress bar at top (numbered, connected by lines)
 *   - Title + description
 *   - Children (step content)
 *   - Back / Next / Done navigation buttons at bottom
 *
 * Step states:
 *   pending   — not yet reached
 *   active    — currently displayed
 *   done      — completed (green ✓)
 *   error     — failed (red ✗)
 */

import type { ReactNode } from 'react'

export type StepStatus = 'pending' | 'active' | 'done' | 'error'

export interface WorkflowStep {
  label: string
  status: StepStatus
}

interface WorkflowShellProps {
  title: string
  icon: string
  steps: WorkflowStep[]
  currentStep: number          // 0-indexed
  onBack?: () => void
  onNext?: () => void
  nextLabel?: string
  nextDisabled?: boolean
  isLoading?: boolean
  onClose: () => void
  children: ReactNode
}

function StepDot({ step, index }: { step: WorkflowStep; index: number }) {
  const bg =
    step.status === 'done'    ? '#3D8D40' :
    step.status === 'active'  ? '#FF7700' :
    step.status === 'error'   ? '#E53935' : '#2E2E2E'

  const text =
    step.status === 'done'  ? '✓' :
    step.status === 'error' ? '✗' : String(index + 1)

  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold flex-shrink-0 border"
        style={{ background: bg, borderColor: bg, color: '#fff' }}
      >
        {text}
      </div>
      <span
        className="text-[8px] uppercase tracking-[0.04em] text-center leading-tight"
        style={{
          color: step.status === 'active' ? '#FF7700' :
                 step.status === 'done'   ? '#3D8D40' :
                 step.status === 'error'  ? '#E53935' : '#666666',
          maxWidth: '40px',
        }}
      >
        {step.label}
      </span>
    </div>
  )
}

export function WorkflowShell({
  title, icon, steps, currentStep,
  onBack, onNext, nextLabel = 'Next →',
  nextDisabled = false, isLoading = false,
  onClose, children,
}: WorkflowShellProps) {
  return (
    <div className="h-full flex flex-col bg-push-bg">

      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-push-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-push-orange text-base">{icon}</span>
          <span className="text-[11px] uppercase tracking-[0.08em] text-push-text font-medium">
            {title}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-push-muted hover:text-push-text text-[10px] leading-none"
          title="Close workflow"
        >
          ✕
        </button>
      </div>

      {/* ── Step progress bar ──────────────────────────────────────── */}
      <div className="flex items-start justify-center gap-0 px-4 py-3 border-b border-push-border flex-shrink-0">
        {steps.map((step, i) => (
          <div key={i} className="flex items-center">
            <StepDot step={step} index={i} />
            {i < steps.length - 1 && (
              <div
                className="h-px w-6 mt-[-12px] flex-shrink-0"
                style={{
                  background: steps[i].status === 'done' ? '#3D8D40' : '#2E2E2E'
                }}
              />
            )}
          </div>
        ))}
      </div>

      {/* ── Step content ─────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        {children}
      </div>

      {/* ── Navigation footer ─────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2 border-t border-push-border flex-shrink-0">
        {onBack ? (
          <button
            onClick={onBack}
            disabled={isLoading}
            className="px-3 py-1 text-[10px] uppercase tracking-[0.06em] text-push-muted
                       hover:text-push-text disabled:opacity-40 transition-colors"
          >
            ← Back
          </button>
        ) : <div />}

        <span className="text-[9px] text-push-muted">
          Step {currentStep + 1} of {steps.length}
        </span>

        {onNext && (
          <button
            onClick={onNext}
            disabled={nextDisabled || isLoading}
            className="px-3 py-1 rounded-[3px] border text-[10px] uppercase tracking-[0.06em]
                       border-push-orange text-push-orange
                       hover:bg-push-orange hover:text-push-bg
                       disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? '…' : nextLabel}
          </button>
        )}
      </div>
    </div>
  )
}
