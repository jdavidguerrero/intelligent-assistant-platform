/**
 * MasterWorkflow — 5-step mastering readiness check.
 *
 * Steps:
 *   0 Input     — file path + genre selection
 *   1 Analyze   — call analyzeMaster → auto-advance to Readiness on success
 *   2 Readiness — readiness score, LUFS panel, issues list
 *   3 Chain     — mastering chain per processor + optional Claude tips stream
 *   4 Done      — summary badge + close
 */

import React, { useState, useEffect, useRef } from 'react'
import { WorkflowShell } from './WorkflowShell'
import type { WorkflowStep } from './WorkflowShell'
import { mcpClient } from '../../services/mcpClient'
import type { MasterReport } from '../../services/mcpClient'
import { SUPPORTED_GENRES } from '../../types/analysis'
import { useWorkflowStore } from '../../store/workflowStore'

// ── Shared helpers ────────────────────────────────────────────────────────────

function LoadingSpinner({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10">
      <div className="w-6 h-6 rounded-full border-2 border-push-border border-t-push-orange animate-spin" />
      <span className="text-[10px] text-push-muted uppercase tracking-[0.08em]">{label}</span>
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[9px] uppercase tracking-[0.08em] text-push-muted block mb-1">
      {children}
    </span>
  )
}

const inputClass = `
  w-full bg-push-elevated border border-push-border rounded-[3px]
  text-[11px] text-push-text px-2 py-1.5
  placeholder:text-push-muted
  focus:outline-none focus:border-push-orange transition-colors
`

const selectClass = `
  w-full bg-push-elevated border border-push-border rounded-[3px]
  text-[11px] text-push-text px-2 py-1.5
  focus:outline-none focus:border-push-orange transition-colors
`

// ── Step 0: Input ─────────────────────────────────────────────────────────────

interface InputStepProps {
  filePath: string
  genre: string
  onFilePathChange: (v: string) => void
  onGenreChange: (v: string) => void
  onNext: () => void
}

function InputStep({ filePath, genre, onFilePathChange, onGenreChange, onNext }: InputStepProps) {
  return (
    <div className="p-4 flex flex-col gap-4">
      <div>
        <SectionLabel>Pre-Master File Path</SectionLabel>
        <input
          type="text"
          className={inputClass}
          value={filePath}
          onChange={e => onFilePathChange(e.target.value)}
          placeholder="/path/to/pre-master.wav"
          spellCheck={false}
        />
        <p className="text-[9px] text-push-muted mt-1 leading-relaxed">
          Provide the pre-master bounce — the track before the mastering limiter.
        </p>
      </div>

      <div>
        <SectionLabel>Genre</SectionLabel>
        <select className={selectClass} value={genre} onChange={e => onGenreChange(e.target.value)}>
          {SUPPORTED_GENRES.map(g => <option key={g} value={g}>{g}</option>)}
        </select>
      </div>

      <button
        onClick={onNext}
        disabled={filePath.trim() === ''}
        className="self-start px-4 py-1.5 rounded-[3px] border border-push-orange text-push-orange
                   text-[10px] uppercase tracking-[0.06em]
                   hover:bg-push-orange hover:text-push-bg
                   disabled:opacity-40 disabled:cursor-not-allowed
                   transition-colors"
      >
        Next →
      </button>
    </div>
  )
}

// ── Step 1: Analyze ───────────────────────────────────────────────────────────

interface AnalyzeStepProps {
  error: string | null
  onRetry: () => void
}

function AnalyzeStep({ error, onRetry }: AnalyzeStepProps) {
  if (error) {
    return (
      <div className="p-4 flex flex-col gap-2">
        <span className="text-[10px] text-push-red">{error}</span>
        <button
          onClick={onRetry}
          className="self-start px-3 py-1 rounded-[3px] border border-push-orange text-push-orange
                     text-[10px] uppercase tracking-[0.06em]
                     hover:bg-push-orange hover:text-push-bg transition-colors"
        >
          Try Again
        </button>
      </div>
    )
  }
  return <LoadingSpinner label="Measuring LUFS, true peak, crest factor…" />
}

// ── Step 2: Readiness ─────────────────────────────────────────────────────────

interface ReadinessStepProps {
  report: MasterReport
}

function lufsColor(lufs: number): string {
  if (lufs >= -14 && lufs <= -9) return 'text-push-green'
  if ((lufs >= -16 && lufs < -14) || (lufs > -9 && lufs <= -6)) return 'text-push-yellow'
  return 'text-push-red'
}

function readinessColor(score: number): string {
  if (score >= 80) return 'text-push-green'
  if (score >= 60) return 'text-push-yellow'
  return 'text-push-red'
}

function readinessSubtitle(score: number): string {
  if (score >= 80) return 'Ready for distribution'
  if (score >= 60) return 'Almost there — fix the flagged issues'
  return 'Significant work needed'
}

function ReadinessStep({ report }: ReadinessStepProps) {
  const { lufs_integrated, true_peak_db, inter_sample_peaks } = report.loudness
  const { crest_factor_db } = report.dynamics
  const score = report.readiness_score

  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Score */}
      <div className="flex flex-col items-center gap-1 py-3">
        <span className={`text-5xl font-bold font-mono ${readinessColor(score)}`}>
          {score}
        </span>
        <span className="text-[10px] text-push-muted">/ 100 &nbsp; Master Readiness</span>
        <span className="text-[9px] uppercase tracking-[0.08em] text-push-muted mt-0.5">
          {readinessSubtitle(score)}
        </span>
      </div>

      {/* LUFS panel */}
      <div className="bg-push-surface border border-push-border rounded-[3px] p-3 flex flex-col gap-2">
        <SectionLabel>Loudness</SectionLabel>

        {/* Integrated LUFS */}
        <div className="flex items-baseline justify-between">
          <span className="text-[9px] text-push-muted">Integrated LUFS</span>
          <div className="flex items-baseline gap-2">
            <span className={`text-[14px] font-mono font-bold ${lufsColor(lufs_integrated)}`}>
              {lufs_integrated.toFixed(1)}
            </span>
            <span className="text-[9px] text-push-muted">LU</span>
          </div>
        </div>
        <p className="text-[9px] text-push-muted -mt-1">Target: -14 to -9 LUFS</p>

        {/* True peak */}
        <div className="flex items-baseline justify-between">
          <span className="text-[9px] text-push-muted">True Peak</span>
          <span className={`text-[12px] font-mono ${true_peak_db > -1 ? 'text-push-red' : 'text-push-green'}`}>
            {true_peak_db.toFixed(1)} dBTP
          </span>
        </div>
        <p className="text-[9px] text-push-muted -mt-1">Target: &lt; -1 dBTP</p>

        {/* Inter-sample peaks */}
        <div className="flex items-center justify-between">
          <span className="text-[9px] text-push-muted">Inter-Sample Peaks</span>
          {inter_sample_peaks ? (
            <span className="text-[9px] px-2 py-0.5 bg-red-900/30 border border-push-red rounded text-push-red">
              Inter-sample peaks detected
            </span>
          ) : (
            <span className="text-[9px] px-2 py-0.5 bg-green-900/30 border border-push-green rounded text-push-green">
              Clean
            </span>
          )}
        </div>

        {/* Crest factor */}
        <div className="flex items-baseline justify-between">
          <span className="text-[9px] text-push-muted">Crest Factor</span>
          <span className="text-[12px] font-mono text-push-text">
            {crest_factor_db.toFixed(1)} dB
          </span>
        </div>
      </div>

      {/* Issues */}
      {report.issues.length > 0 && (
        <div className="flex flex-col gap-1">
          <SectionLabel>Issues ({report.issues.length})</SectionLabel>
          <div className="flex flex-wrap gap-1">
            {report.issues.map((issue, i) => (
              <span
                key={i}
                className="text-[10px] px-2 py-0.5 bg-red-900/30 border border-push-red rounded text-push-red"
              >
                {issue}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Step 3: Chain ─────────────────────────────────────────────────────────────

interface ChainStepProps {
  report: MasterReport
}

function ChainStep({ report }: ChainStepProps) {
  const [streaming, setStreaming] = useState(false)
  const [streamText, setStreamText] = useState('')
  const streamRef = useRef<HTMLDivElement>(null)
  const { mastering_chain } = report

  const handleAskClaude = async () => {
    setStreaming(true)
    setStreamText('')
    try {
      const gen = mcpClient.askStream({
        query: `Mastering chain for ${report.genre}: explain each stage and key settings`,
        use_tools: false,
      })
      for await (const event of gen) {
        if (event.type === 'chunk') {
          setStreamText(prev => {
            const next = prev + event.content
            // Scroll to bottom on next paint
            requestAnimationFrame(() => {
              if (streamRef.current) {
                streamRef.current.scrollTop = streamRef.current.scrollHeight
              }
            })
            return next
          })
        }
      }
    } catch (e) {
      setStreamText(prev => prev + '\n\n[Error: ' + (e instanceof Error ? e.message : 'stream failed') + ']')
    } finally {
      setStreaming(false)
    }
  }

  return (
    <div className="p-4 flex flex-col gap-3">
      {/* Chain header */}
      <div className="bg-push-surface border border-push-border rounded-[3px] p-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] text-push-orange uppercase tracking-[0.06em]">
            {mastering_chain.genre}
          </span>
          <span className="text-[9px] text-push-muted">·</span>
          <span className="text-[9px] text-push-muted uppercase tracking-[0.06em]">
            {mastering_chain.stage}
          </span>
        </div>
        <p className="text-[10px] text-push-muted leading-relaxed">
          {mastering_chain.description}
        </p>
      </div>

      {/* Processors */}
      <div className="flex flex-col gap-1">
        <SectionLabel>Processors ({mastering_chain.processors.length})</SectionLabel>
        {mastering_chain.processors.map((proc, i) => (
          <div
            key={i}
            className="bg-push-surface border border-push-border rounded-[3px] p-2 mb-1"
          >
            {/* Name + type */}
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[11px] text-push-text font-medium">{proc.name}</span>
              <span className="text-[9px] text-push-muted uppercase tracking-[0.06em]">
                {proc.proc_type}
              </span>
            </div>
            {/* Plugin */}
            <div className="text-[10px] mb-1">
              <span className="text-push-orange">{proc.plugin_primary}</span>
              {proc.plugin_fallback && (
                <span className="text-push-muted"> ({proc.plugin_fallback})</span>
              )}
            </div>
            {/* Parameters */}
            {proc.params.length > 0 && (
              <div className="flex flex-col gap-0.5">
                {proc.params.map((param, pi) => (
                  <span key={pi} className="text-[9px] font-mono text-push-muted">
                    {param.name}: {param.value}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <p className="text-[9px] text-push-muted italic">
        This chain is a starting point — adjust to taste.
      </p>

      {/* Ask Claude button */}
      <button
        onClick={() => { void handleAskClaude() }}
        disabled={streaming}
        className="self-start px-3 py-1 rounded-[3px] border border-push-blue text-push-blue
                   text-[10px] uppercase tracking-[0.06em]
                   hover:bg-push-blue hover:text-push-bg
                   disabled:opacity-40 disabled:cursor-not-allowed
                   transition-colors"
      >
        {streaming ? '…Streaming' : 'Ask Claude for Tips'}
      </button>

      {/* Stream output */}
      {(streaming || streamText) && (
        <div
          ref={streamRef}
          className="bg-push-surface border border-push-border rounded-[3px] p-2
                     text-[10px] text-push-text leading-relaxed
                     max-h-48 overflow-y-auto whitespace-pre-wrap font-mono"
        >
          {streamText}
          {streaming && <span className="animate-pulse text-push-orange">▍</span>}
        </div>
      )}
    </div>
  )
}

// ── Step 4: Done ──────────────────────────────────────────────────────────────

interface DoneStepProps {
  report: MasterReport
  onClose: () => void
}

function DoneStep({ report, onClose }: DoneStepProps) {
  const score = report.readiness_score
  const { mastering_chain } = report

  return (
    <div className="p-4 flex flex-col gap-4">
      <SectionLabel>Summary</SectionLabel>

      <div className="bg-push-surface border border-push-border rounded-[3px] p-3 flex flex-col gap-2">
        {/* Readiness score badge */}
        <div className="flex items-center justify-between">
          <span className="text-[9px] text-push-muted uppercase tracking-[0.06em]">Readiness</span>
          <span className={`text-[13px] font-mono font-bold ${readinessColor(score)}`}>
            {score} / 100
          </span>
        </div>

        {/* LUFS */}
        <div className="flex items-center justify-between">
          <span className="text-[9px] text-push-muted uppercase tracking-[0.06em]">LUFS Integrated</span>
          <span className={`text-[12px] font-mono ${lufsColor(report.loudness.lufs_integrated)}`}>
            {report.loudness.lufs_integrated.toFixed(1)} LU
          </span>
        </div>

        {/* Issues */}
        <div className="flex items-center justify-between">
          <span className="text-[9px] text-push-muted uppercase tracking-[0.06em]">Issues</span>
          <span className={`text-[12px] font-mono ${report.issues.length > 0 ? 'text-push-red' : 'text-push-green'}`}>
            {report.issues.length}
          </span>
        </div>

        {/* Chain */}
        <div className="flex items-center justify-between">
          <span className="text-[9px] text-push-muted uppercase tracking-[0.06em]">Chain</span>
          <span className="text-[10px] text-push-orange">
            {mastering_chain.genre} — {mastering_chain.stage}
          </span>
        </div>
      </div>

      <button
        onClick={onClose}
        className="w-full py-2 rounded-[3px] bg-push-orange text-push-bg
                   text-[10px] uppercase tracking-[0.06em] font-medium
                   hover:opacity-90 transition-opacity"
      >
        Close
      </button>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function MasterWorkflow() {
  const { setWorkflow } = useWorkflowStore()

  const [step, setStep] = useState(0)
  const [filePath, setFilePath] = useState('')
  const [genre, setGenre] = useState(SUPPORTED_GENRES[0] ?? 'organic house')
  const [analyzeError, setAnalyzeError] = useState<string | null>(null)
  const [masterReport, setMasterReport] = useState<MasterReport | null>(null)

  // ── Step 1 — run analysis ─────────────────────────────────────────────────
  const runAnalysis = async () => {
    setAnalyzeError(null)
    try {
      const report = await mcpClient.analyzeMaster({ file_path: filePath, genre })
      setMasterReport(report)
      setStep(2)  // auto-advance to Readiness
    } catch (e) {
      setAnalyzeError(e instanceof Error ? e.message : 'Analysis failed')
    }
  }

  useEffect(() => {
    if (step === 1 && filePath.trim() !== '') {
      void runAnalysis()
    }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Step definitions ──────────────────────────────────────────────────────
  const STEP_LABELS = ['Input', 'Analyze', 'Readiness', 'Chain', 'Done']
  const steps: WorkflowStep[] = STEP_LABELS.map((label, i) => ({
    label,
    status: i < step ? 'done' : i === step ? 'active' : 'pending',
  }))

  // ── Navigation ────────────────────────────────────────────────────────────
  const showBack = step === 2 || step === 3
  const showNext = step === 2 || step === 3

  const handleBack = () => {
    if (step === 2) setStep(0)
    else if (step === 3) setStep(2)
  }

  const handleNext = () => {
    if (step === 2) setStep(3)
    else if (step === 3) setStep(4)
  }

  const nextLabel = step === 3 ? 'Done →' : 'View Chain →'

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <WorkflowShell
      title="Master Readiness"
      icon="◎"
      steps={steps}
      currentStep={step}
      onBack={showBack ? handleBack : undefined}
      onNext={showNext ? handleNext : undefined}
      nextLabel={nextLabel}
      isLoading={step === 1 && !analyzeError}
      onClose={() => setWorkflow(null)}
    >
      {step === 0 && (
        <InputStep
          filePath={filePath}
          genre={genre}
          onFilePathChange={setFilePath}
          onGenreChange={setGenre}
          onNext={() => setStep(1)}
        />
      )}

      {step === 1 && (
        <AnalyzeStep
          error={analyzeError}
          onRetry={() => setStep(0)}
        />
      )}

      {step === 2 && masterReport && (
        <ReadinessStep report={masterReport} />
      )}

      {step === 3 && masterReport && (
        <ChainStep report={masterReport} />
      )}

      {step === 4 && masterReport && (
        <DoneStep
          report={masterReport}
          onClose={() => setWorkflow(null)}
        />
      )}
    </WorkflowShell>
  )
}
