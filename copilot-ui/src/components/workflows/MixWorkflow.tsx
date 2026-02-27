/**
 * MixWorkflow — 5-step guided mix diagnosis and fix workflow.
 *
 * Steps:
 *   0 Input    — file path + genre selection
 *   1 Analyze  — call analyzeMix → auto-advance to Problems on success
 *   2 Problems — display problems sorted by severity
 *   3 Fix      — per-recommendation fix application via Ableton MCP tool
 *   4 Compare  — re-analyze and show before/after diff
 */

import React, { useState, useEffect } from 'react'
import { WorkflowShell } from './WorkflowShell'
import type { WorkflowStep } from './WorkflowShell'
import { mcpClient } from '../../services/mcpClient'
import type { MixReport, Recommendation } from '../../types/analysis'
import { SUPPORTED_GENRES } from '../../types/analysis'
import { useWorkflowStore } from '../../store/workflowStore'

// ── Types ─────────────────────────────────────────────────────────────────────

type FixStatus = 'pending' | 'loading' | 'success' | 'error'

// ── Helpers ──────────────────────────────────────────────────────────────────

function LoadingSpinner({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10">
      <div
        className="w-6 h-6 rounded-full border-2 border-push-border border-t-push-orange animate-spin"
      />
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

function SeverityBadge({ severity }: { severity: number }) {
  const color =
    severity >= 7 ? 'border-push-red text-push-red' :
    severity >= 4 ? 'border-push-yellow text-push-yellow' :
                    'border-push-green text-push-green'
  return (
    <span className={`px-1.5 py-0.5 rounded-[3px] border text-[9px] font-mono flex-shrink-0 ${color}`}>
      {severity}
    </span>
  )
}

function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center bg-push-elevated border border-push-border rounded-[3px] px-2 py-1">
      <span className="text-[8px] uppercase tracking-[0.08em] text-push-muted">{label}</span>
      <span className="text-[11px] text-push-text font-mono">{value}</span>
    </div>
  )
}

// ── Step 0: Input ─────────────────────────────────────────────────────────────

interface InputStepProps {
  filePath: string
  genre: string
  onFilePathChange: (v: string) => void
  onGenreChange: (v: string) => void
  onAnalyze: () => void
}

function InputStep({ filePath, genre, onFilePathChange, onGenreChange, onAnalyze }: InputStepProps) {
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

  return (
    <div className="p-4 flex flex-col gap-4">
      <div>
        <SectionLabel>Mix File Path</SectionLabel>
        <input
          type="text"
          className={inputClass}
          value={filePath}
          onChange={e => onFilePathChange(e.target.value)}
          placeholder="/path/to/bounce.wav"
          spellCheck={false}
        />
        <p className="text-[9px] text-push-muted mt-1 leading-relaxed">
          Enter the absolute path to your mix on this machine's filesystem.
        </p>
      </div>

      <div>
        <SectionLabel>Genre</SectionLabel>
        <select className={selectClass} value={genre} onChange={e => onGenreChange(e.target.value)}>
          {SUPPORTED_GENRES.map(g => <option key={g} value={g}>{g}</option>)}
        </select>
      </div>

      <button
        onClick={onAnalyze}
        disabled={filePath.trim() === ''}
        className="self-start px-4 py-1.5 rounded-[3px] border border-push-orange text-push-orange
                   text-[10px] uppercase tracking-[0.06em]
                   hover:bg-push-orange hover:text-push-bg
                   disabled:opacity-40 disabled:cursor-not-allowed
                   transition-colors"
      >
        Analyze →
      </button>
    </div>
  )
}

// ── Step 1: Analyze (auto-runs, then forwards) ────────────────────────────────

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
  return <LoadingSpinner label="Analyzing your mix…" />
}

// ── Step 2: Problems ──────────────────────────────────────────────────────────

interface ProblemsStepProps {
  report: MixReport
}

function ProblemsStep({ report }: ProblemsStepProps) {
  const sorted = [...report.problems].sort((a, b) => b.severity - a.severity)

  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Summary pills */}
      <div className="flex gap-2 flex-wrap">
        <MetricPill label="LUFS" value={`${report.dynamics.lufs.toFixed(1)} LU`} />
        <MetricPill label="Peak" value={`${report.dynamics.peak_db.toFixed(1)} dB`} />
        <MetricPill label="Genre" value={report.genre} />
        <MetricPill label="Centroid" value={`${Math.round(report.spectral.spectral_centroid_hz)} Hz`} />
        <MetricPill label="Tilt" value={`${report.spectral.spectral_tilt_db_oct.toFixed(1)} dB/oct`} />
      </div>

      {/* Problem count */}
      <div className="flex items-center gap-2">
        <SectionLabel>Problems</SectionLabel>
        <span className="text-[9px] text-push-muted">
          {sorted.length} {sorted.length === 1 ? 'problem' : 'problems'} found
        </span>
      </div>

      {sorted.length === 0 ? (
        <div className="bg-push-surface border border-push-green rounded-[3px] p-3">
          <span className="text-[11px] text-push-green">No problems detected ✓</span>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {sorted.map((problem, i) => (
            <div
              key={i}
              className="bg-push-surface border border-push-border rounded-[3px] p-3 flex flex-col gap-1"
            >
              <div className="flex items-center gap-2">
                <SeverityBadge severity={problem.severity} />
                <span className="text-[10px] text-push-orange uppercase tracking-[0.06em]">
                  {problem.category}
                </span>
              </div>
              <p className="text-[11px] text-push-text leading-relaxed">{problem.description}</p>
              <p className="text-[10px] text-push-muted leading-relaxed">{problem.recommendation}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Step 3: Fix ───────────────────────────────────────────────────────────────

interface FixStepProps {
  report: MixReport
  fixStatus: Record<number, FixStatus>
  fixErrors: Record<number, string>
  onApplyFix: (index: number, rec: Recommendation) => void
}

function FixStep({ report, fixStatus, fixErrors, onApplyFix }: FixStepProps) {
  const sorted = [...report.recommendations].sort((a, b) => b.severity - a.severity)

  if (sorted.length === 0) {
    return (
      <div className="p-4">
        <div className="bg-push-surface border border-push-green rounded-[3px] p-3">
          <span className="text-[11px] text-push-green">No recommendations — mix looks good ✓</span>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 flex flex-col gap-3">
      <SectionLabel>Recommendations ({sorted.length})</SectionLabel>
      {sorted.map((rec, i) => {
        const status = fixStatus[i] ?? 'pending'
        const err = fixErrors[i]
        return (
          <div
            key={i}
            className="bg-push-surface border border-push-border rounded-[3px] p-3 flex flex-col gap-2"
          >
            {/* Header */}
            <div className="flex items-center gap-2">
              <SeverityBadge severity={rec.severity} />
              <span className="text-[10px] text-push-orange uppercase tracking-[0.06em]">
                {rec.problem_category}
              </span>
              <div className="flex-1" />
              {status === 'success' && (
                <span className="text-[9px] text-push-green uppercase tracking-[0.06em]">✓ Applied</span>
              )}
              {status === 'error' && (
                <span className="text-[9px] text-push-red uppercase tracking-[0.06em]">✗ Failed</span>
              )}
              {status === 'loading' && (
                <span className="text-[9px] text-push-muted uppercase tracking-[0.06em] animate-pulse">
                  Applying…
                </span>
              )}
            </div>

            {/* Summary */}
            <p className="text-[11px] text-push-text leading-relaxed">{rec.summary}</p>

            {/* Steps */}
            {rec.steps && rec.steps.length > 0 && (
              <div className="flex flex-col gap-1 mt-1">
                {rec.steps.map((s, si) => (
                  <div
                    key={si}
                    className="flex gap-2 items-start bg-push-elevated rounded-[2px] px-2 py-1"
                  >
                    <span className="text-[9px] text-push-muted flex-shrink-0">{s.bus}</span>
                    <span className="text-[9px] text-push-text">{s.action}</span>
                    {s.plugin_primary && (
                      <span className="text-[9px] text-push-orange ml-auto flex-shrink-0">
                        {s.plugin_primary}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Error message */}
            {err && (
              <p className="text-[10px] text-push-red">{err}</p>
            )}

            {/* Apply button */}
            <button
              onClick={() => onApplyFix(i, rec)}
              disabled={status === 'loading' || status === 'success'}
              className="self-start px-3 py-1 rounded-[3px] border border-push-orange text-push-orange
                         text-[10px] uppercase tracking-[0.06em]
                         hover:bg-push-orange hover:text-push-bg
                         disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors"
            >
              {status === 'loading' ? '…' : status === 'success' ? '✓ Applied' : 'Apply Fix'}
            </button>
          </div>
        )
      })}
    </div>
  )
}

// ── Step 4: Compare ───────────────────────────────────────────────────────────

interface CompareStepProps {
  loading: boolean
  error: string | null
  before: MixReport
  after: MixReport | null
  onDone: () => void
}

function CompareStep({ loading, error, before, after, onDone }: CompareStepProps) {
  if (loading) return <LoadingSpinner label="Re-analyzing mix…" />
  if (error) {
    return (
      <div className="p-4">
        <span className="text-[10px] text-push-red">{error}</span>
      </div>
    )
  }
  if (!after) return null

  const beforeProblems = before.problems.length
  const afterProblems = after.problems.length
  const lufsImproved = Math.abs(after.dynamics.lufs) < Math.abs(before.dynamics.lufs)
  const peakImproved = after.dynamics.peak_db <= before.dynamics.peak_db
  const problemsImproved = afterProblems <= beforeProblems

  function DeltaValue({
    label, before: bv, after: av, improved,
  }: { label: string; before: string; after: string; improved: boolean }) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-[9px] text-push-muted w-20 flex-shrink-0">{label}</span>
        <span className="text-[11px] text-push-muted font-mono">{bv}</span>
        <span className="text-[9px] text-push-muted">→</span>
        <span
          className={`text-[11px] font-mono ${improved ? 'text-push-green' : 'text-push-red'}`}
        >
          {av}
        </span>
      </div>
    )
  }

  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Column headers */}
      <div className="flex gap-4">
        <div className="flex-1">
          <SectionLabel>Before</SectionLabel>
        </div>
        <div className="flex-1">
          <SectionLabel>After</SectionLabel>
        </div>
      </div>

      {/* Metrics comparison */}
      <div className="bg-push-surface border border-push-border rounded-[3px] p-3 flex flex-col gap-2">
        <DeltaValue
          label="LUFS"
          before={`${before.dynamics.lufs.toFixed(1)} LU`}
          after={`${after.dynamics.lufs.toFixed(1)} LU`}
          improved={lufsImproved}
        />
        <DeltaValue
          label="Peak dB"
          before={`${before.dynamics.peak_db.toFixed(1)} dB`}
          after={`${after.dynamics.peak_db.toFixed(1)} dB`}
          improved={peakImproved}
        />
        <DeltaValue
          label="Problems"
          before={String(beforeProblems)}
          after={String(afterProblems)}
          improved={problemsImproved}
        />
      </div>

      {/* Overall verdict */}
      {problemsImproved ? (
        <div className="bg-push-surface border border-push-green rounded-[3px] px-3 py-2">
          <span className="text-[11px] text-push-green">✓ Mix improved</span>
        </div>
      ) : (
        <div className="bg-push-surface border border-push-border rounded-[3px] px-3 py-2">
          <span className="text-[11px] text-push-muted">No measurable improvement detected.</span>
        </div>
      )}

      <button
        onClick={onDone}
        className="self-start px-4 py-1.5 rounded-[3px] bg-push-orange text-push-bg
                   text-[10px] uppercase tracking-[0.06em] font-medium
                   hover:opacity-90 transition-opacity"
      >
        Done
      </button>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function MixWorkflow() {
  const { setWorkflow } = useWorkflowStore()

  // Input
  const [step, setStep] = useState(0)
  const [filePath, setFilePath] = useState('')
  const [genre, setGenre] = useState(SUPPORTED_GENRES[0] ?? 'organic house')

  // Analysis
  const [analyzeError, setAnalyzeError] = useState<string | null>(null)
  const [beforeReport, setBeforeReport] = useState<MixReport | null>(null)

  // Fix
  const [fixStatus, setFixStatus] = useState<Record<number, FixStatus>>({})
  const [fixErrors, setFixErrors] = useState<Record<number, string>>({})

  // Compare
  const [compareLoading, setCompareLoading] = useState(false)
  const [compareError, setCompareError] = useState<string | null>(null)
  const [afterReport, setAfterReport] = useState<MixReport | null>(null)

  // ── Step 1 — run analysis ─────────────────────────────────────────────────
  const runAnalysis = async () => {
    setAnalyzeError(null)
    try {
      const report = await mcpClient.analyzeMix({ file_path: filePath, genre })
      setBeforeReport(report)
      setStep(2)  // auto-advance to Problems
    } catch (e) {
      setAnalyzeError(e instanceof Error ? e.message : 'Analysis failed')
    }
  }

  useEffect(() => {
    if (step === 1 && filePath.trim() !== '') {
      void runAnalysis()
    }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Step 4 — re-analyze for compare ──────────────────────────────────────
  const runCompare = async () => {
    setCompareLoading(true)
    setCompareError(null)
    setAfterReport(null)
    try {
      const report = await mcpClient.analyzeMix({ file_path: filePath, genre })
      setAfterReport(report)
    } catch (e) {
      setCompareError(e instanceof Error ? e.message : 'Re-analysis failed')
    } finally {
      setCompareLoading(false)
    }
  }

  useEffect(() => {
    if (step === 4) {
      void runCompare()
    }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Apply fix handler ─────────────────────────────────────────────────────
  const handleApplyFix = async (index: number, rec: Recommendation) => {
    setFixStatus(prev => ({ ...prev, [index]: 'loading' }))
    try {
      const res = await mcpClient.callTool({
        name: 'ableton_apply_mix_fix',
        params: {
          track_name: 'Master',
          category: rec.problem_category,
          recommendation: rec.summary,
          dry_run: false,
        },
      })
      if (res.success) {
        setFixStatus(prev => ({ ...prev, [index]: 'success' }))
      } else {
        setFixStatus(prev => ({ ...prev, [index]: 'error' }))
        setFixErrors(prev => ({ ...prev, [index]: res.error ?? 'Fix failed' }))
      }
    } catch (e) {
      setFixStatus(prev => ({ ...prev, [index]: 'error' }))
      setFixErrors(prev => ({
        ...prev,
        [index]: e instanceof Error ? e.message : 'Unknown error',
      }))
    }
  }

  // ── Step definitions ──────────────────────────────────────────────────────
  const STEP_LABELS = ['Input', 'Analyze', 'Problems', 'Fix', 'Compare']
  const steps: WorkflowStep[] = STEP_LABELS.map((label, i) => ({
    label,
    status: i < step ? 'done' : i === step ? 'active' : 'pending',
  }))

  // ── Navigation ────────────────────────────────────────────────────────────
  // Step 1 is fully auto — no manual back/next shown while loading
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

  const nextLabel = step === 3 ? 'Re-Analyze →' : 'Fix Problems →'

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <WorkflowShell
      title="Mix Diagnosis"
      icon="⊞"
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
          onAnalyze={() => setStep(1)}
        />
      )}

      {step === 1 && (
        <AnalyzeStep
          error={analyzeError}
          onRetry={() => setStep(0)}
        />
      )}

      {step === 2 && beforeReport && (
        <ProblemsStep report={beforeReport} />
      )}

      {step === 3 && beforeReport && (
        <FixStep
          report={beforeReport}
          fixStatus={fixStatus}
          fixErrors={fixErrors}
          onApplyFix={(i, rec) => { void handleApplyFix(i, rec) }}
        />
      )}

      {step === 4 && beforeReport && (
        <CompareStep
          loading={compareLoading}
          error={compareError}
          before={beforeReport}
          after={afterReport}
          onDone={() => setWorkflow(null)}
        />
      )}
    </WorkflowShell>
  )
}
