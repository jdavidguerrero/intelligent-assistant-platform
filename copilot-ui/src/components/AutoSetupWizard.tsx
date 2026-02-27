/**
 * AutoSetupWizard — 6-step wizard for the auto_setup_mix pipeline.
 *
 * Steps:
 *   0 Config      — Genre selector + optional master file path + dry_run toggle
 *   1 Capture     — Calls auto_setup_mix dry_run=true. Shows "Analysing stems…" spinner.
 *   2 Stems        — Grid of stem type cards with footprint and problem badges.
 *   3 Attribution — Stacked bar per problem category showing contributing stems.
 *   4 Preview     — Checkbox list of setup_actions grouped by track.
 *   5 Apply       — Call auto_setup_mix dry_run=false (or dry_run summary).
 */

import React, { useState, useEffect } from 'react'
import { WorkflowShell } from './workflows/WorkflowShell'
import type { WorkflowStep } from './workflows/WorkflowShell'
import { mcpClient } from '../services/mcpClient'
import { SUPPORTED_GENRES } from '../types/analysis'
import StemAnalysisView from './StemAnalysisView'
import type { StemData, ContributionData } from './StemAnalysisView'

// ── Types ─────────────────────────────────────────────────────────────────────

interface SetupAction {
  track_name: string
  device_name: string
  parameter_name: string
  value: string | number
}

interface ApplyActionResult {
  track_name: string
  device_name: string
  parameter_name: string
  value: string | number
  status: 'applied' | 'error'
  error?: string
}

interface AutoSetupResult {
  stems: StemData[]
  attribution: Record<string, ContributionData[]>
  setup_actions: SetupAction[]
  summary?: string
}

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

const inputClass = [
  'w-full bg-push-elevated border border-push-border rounded-[3px]',
  'text-[11px] text-push-text px-2 py-1.5',
  'placeholder:text-push-muted',
  'focus:outline-none focus:border-push-orange transition-colors',
].join(' ')

const selectClass = [
  'w-full bg-push-elevated border border-push-border rounded-[3px]',
  'text-[11px] text-push-text px-2 py-1.5',
  'focus:outline-none focus:border-push-orange transition-colors',
].join(' ')

// ── Step 0: Config ────────────────────────────────────────────────────────────

interface ConfigStepProps {
  genre: string
  masterFilePath: string
  dryRun: boolean
  onGenreChange: (v: string) => void
  onMasterFilePathChange: (v: string) => void
  onDryRunChange: (v: boolean) => void
  onNext: () => void
}

function ConfigStep({
  genre,
  masterFilePath,
  dryRun,
  onGenreChange,
  onMasterFilePathChange,
  onDryRunChange,
  onNext,
}: ConfigStepProps) {
  return (
    <div className="p-4 flex flex-col gap-4">
      <div>
        <SectionLabel>Genre</SectionLabel>
        <select
          className={selectClass}
          value={genre}
          onChange={e => onGenreChange(e.target.value)}
        >
          {SUPPORTED_GENRES.map(g => (
            <option key={g} value={g}>{g}</option>
          ))}
        </select>
      </div>

      <div>
        <SectionLabel>Master File Path (optional)</SectionLabel>
        <input
          type="text"
          className={inputClass}
          value={masterFilePath}
          onChange={e => onMasterFilePathChange(e.target.value)}
          placeholder="/path/to/master.wav"
          spellCheck={false}
        />
        <p className="text-[9px] text-push-muted mt-1 leading-relaxed">
          Leave blank to analyze current Ableton session only.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <button
          role="checkbox"
          aria-checked={dryRun}
          onClick={() => onDryRunChange(!dryRun)}
          className="w-8 h-4 rounded-full flex-shrink-0 border transition-colors relative"
          style={{
            background: dryRun ? '#FF7700' : '#2E2E2E',
            borderColor: dryRun ? '#FF7700' : '#2E2E2E',
          }}
        >
          <span
            className="absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-all"
            style={{ left: dryRun ? '18px' : '2px' }}
          />
        </button>
        <div className="flex flex-col">
          <span className="text-[10px] text-push-text">Dry Run (Preview Only)</span>
          <span className="text-[9px] text-push-muted">
            {dryRun
              ? 'Changes will be previewed but not applied to Ableton.'
              : 'Changes will be applied directly to the session.'}
          </span>
        </div>
      </div>

      <button
        onClick={onNext}
        className="self-start px-4 py-1.5 rounded-[3px] border border-push-orange text-push-orange
                   text-[10px] uppercase tracking-[0.06em]
                   hover:bg-push-orange hover:text-push-bg
                   transition-colors"
      >
        Capture Stems →
      </button>
    </div>
  )
}

// ── Step 1: Capture ───────────────────────────────────────────────────────────

interface CaptureStepProps {
  error: string | null
  onRetry: () => void
}

function CaptureStep({ error, onRetry }: CaptureStepProps) {
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
  return <LoadingSpinner label="Analysing stems…" />
}

// ── Step 2: Stems ─────────────────────────────────────────────────────────────

interface StemsStepProps {
  stems: StemData[]
}

function StemsStep({ stems }: StemsStepProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="px-4 pt-4">
        <SectionLabel>Detected Stems ({stems.length})</SectionLabel>
      </div>
      <StemAnalysisView stems={stems} compact={false} />
    </div>
  )
}

// ── Step 3: Attribution ───────────────────────────────────────────────────────

interface AttributionStepProps {
  attribution: Record<string, ContributionData[]>
}

// Assign a stable color to each stem by index in the contribution list
const CONTRIBUTION_COLORS = [
  '#f97316', // orange
  '#8b5cf6', // purple
  '#22c55e', // green
  '#06b6d4', // cyan
  '#ef4444', // red
  '#eab308', // yellow
  '#ec4899', // pink
  '#6b7280', // gray
]

function AttributionStep({ attribution }: AttributionStepProps) {
  const categories = Object.keys(attribution)

  if (categories.length === 0) {
    return (
      <div className="p-4 text-[10px] text-push-muted italic">No attribution data available.</div>
    )
  }

  return (
    <div className="p-4 flex flex-col gap-4">
      <SectionLabel>Problem Attribution by Stem</SectionLabel>
      {categories.map(category => {
        const contributions = attribution[category] ?? []
        const totalPct = contributions.reduce((acc, c) => acc + c.percentage, 0)

        return (
          <div key={category} className="flex flex-col gap-1">
            {/* Category label */}
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-push-orange uppercase tracking-[0.06em]">
                {category}
              </span>
            </div>

            {/* Stacked bar */}
            <div
              className="h-4 rounded-[2px] flex overflow-hidden border border-push-border"
              title={category}
            >
              {contributions.map((contrib, i) => (
                <div
                  key={contrib.stem_name}
                  style={{
                    width: `${(contrib.percentage / Math.max(totalPct, 1)) * 100}%`,
                    background: CONTRIBUTION_COLORS[i % CONTRIBUTION_COLORS.length],
                    minWidth: contrib.percentage > 0 ? '2px' : '0',
                  }}
                  title={`${contrib.stem_name}: ${contrib.percentage}%`}
                />
              ))}
            </div>

            {/* Legend */}
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              {contributions.map((contrib, i) => (
                <div key={contrib.stem_name} className="flex items-center gap-1">
                  <span
                    className="w-2 h-2 rounded-[1px] flex-shrink-0"
                    style={{ background: CONTRIBUTION_COLORS[i % CONTRIBUTION_COLORS.length] }}
                  />
                  <span className="text-[8px] text-push-muted">
                    {contrib.stem_name} {contrib.percentage}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Step 4: Preview ───────────────────────────────────────────────────────────

interface PreviewStepProps {
  actions: SetupAction[]
  checked: Set<number>
  onToggle: (index: number) => void
}

function PreviewStep({ actions, checked, onToggle }: PreviewStepProps) {
  // Group by track_name
  const grouped: Map<string, Array<{ action: SetupAction; index: number }>> = new Map()
  actions.forEach((action, index) => {
    const list = grouped.get(action.track_name) ?? []
    list.push({ action, index })
    grouped.set(action.track_name, list)
  })

  if (actions.length === 0) {
    return (
      <div className="p-4">
        <div className="bg-push-surface border border-push-green rounded-[3px] p-3">
          <span className="text-[11px] text-push-green">No setup actions required.</span>
        </div>
      </div>
    )
  }

  const checkedCount = checked.size
  const totalCount = actions.length

  return (
    <div className="p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <SectionLabel>Setup Actions</SectionLabel>
        <span className="text-[9px] text-push-muted font-mono">
          {checkedCount}/{totalCount} selected
        </span>
      </div>

      {Array.from(grouped.entries()).map(([trackName, items]) => (
        <div key={trackName} className="flex flex-col gap-1">
          {/* Track header */}
          <span className="text-[10px] text-push-orange uppercase tracking-[0.06em]">
            {trackName}
          </span>

          {/* Actions */}
          {items.map(({ action, index }) => (
            <label
              key={index}
              className="flex items-center gap-2 cursor-pointer bg-push-surface
                         border border-push-border rounded-[3px] px-2 py-1.5
                         hover:border-push-orange transition-colors"
            >
              <input
                type="checkbox"
                checked={checked.has(index)}
                onChange={() => onToggle(index)}
                className="accent-push-orange flex-shrink-0"
              />
              <div className="flex flex-col flex-1 min-w-0">
                <span className="text-[10px] text-push-text truncate">
                  {action.device_name}
                </span>
                <span className="text-[9px] text-push-muted">
                  {action.parameter_name}
                  <span className="ml-2 font-mono text-push-orange">
                    {String(action.value)}
                  </span>
                </span>
              </div>
            </label>
          ))}
        </div>
      ))}
    </div>
  )
}

// ── Step 5: Apply ─────────────────────────────────────────────────────────────

interface ApplyStepProps {
  dryRun: boolean
  loading: boolean
  error: string | null
  results: ApplyActionResult[]
  summary: string | undefined
  onClose: () => void
}

function ApplyStep({ dryRun, loading, error, results, summary, onClose }: ApplyStepProps) {
  if (loading) {
    return <LoadingSpinner label="Applying changes to session…" />
  }

  if (error) {
    return (
      <div className="p-4 flex flex-col gap-2">
        <span className="text-[10px] text-push-red">{error}</span>
      </div>
    )
  }

  if (dryRun) {
    return (
      <div className="p-4 flex flex-col gap-4">
        <div
          className="bg-push-surface border border-push-border rounded-[3px] p-3 flex flex-col gap-2"
        >
          <span className="text-[10px] text-push-orange uppercase tracking-[0.06em]">
            Preview Mode
          </span>
          <p className="text-[11px] text-push-muted leading-relaxed">
            Changes were previewed only — enable Apply to commit.
          </p>
          {summary && (
            <p className="text-[10px] text-push-text leading-relaxed">{summary}</p>
          )}
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

  const appliedCount = results.filter(r => r.status === 'applied').length
  const errorCount = results.filter(r => r.status === 'error').length

  return (
    <div className="p-4 flex flex-col gap-3">
      {/* Summary row */}
      <div className="flex items-center gap-3">
        <span className="text-[10px] text-push-green">{appliedCount} applied</span>
        {errorCount > 0 && (
          <span className="text-[10px] text-push-red">{errorCount} failed</span>
        )}
      </div>

      {/* Per-action results */}
      <div className="flex flex-col gap-1">
        {results.map((result, i) => (
          <div
            key={i}
            className="flex items-center gap-2 bg-push-surface border border-push-border
                       rounded-[3px] px-2 py-1.5"
          >
            <span
              className="text-[10px] font-mono flex-shrink-0"
              style={{ color: result.status === 'applied' ? '#7EB13D' : '#E53935' }}
            >
              {result.status === 'applied' ? '✓' : '✗'}
            </span>
            <div className="flex flex-col flex-1 min-w-0">
              <span className="text-[9px] text-push-muted truncate">
                {result.track_name} / {result.device_name}
              </span>
              <span className="text-[9px] text-push-text truncate">
                {result.parameter_name}
                <span className="ml-1 font-mono text-push-orange">{String(result.value)}</span>
              </span>
              {result.error && (
                <span className="text-[8px] text-push-red">{result.error}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={onClose}
        className="w-full py-2 rounded-[3px] bg-push-orange text-push-bg
                   text-[10px] uppercase tracking-[0.06em] font-medium
                   hover:opacity-90 transition-opacity mt-2"
      >
        Done
      </button>
    </div>
  )
}

// ── Main wizard ───────────────────────────────────────────────────────────────

const STEP_LABELS = ['Config', 'Capture', 'Stems', 'Attribution', 'Preview', 'Apply']

interface AutoSetupWizardProps {
  onClose: () => void
}

export default function AutoSetupWizard({ onClose }: AutoSetupWizardProps) {
  // Step index
  const [step, setStep] = useState(0)

  // Step 0: Config
  const [genre, setGenre] = useState(SUPPORTED_GENRES[0] ?? 'organic house')
  const [masterFilePath, setMasterFilePath] = useState('')
  const [dryRun, setDryRun] = useState(true)

  // Step 1: Capture
  const [captureError, setCaptureError] = useState<string | null>(null)
  const [captureResult, setCaptureResult] = useState<AutoSetupResult | null>(null)

  // Step 4: Preview — checked action indices
  const [checkedActions, setCheckedActions] = useState<Set<number>>(new Set())

  // Step 5: Apply
  const [applyLoading, setApplyLoading] = useState(false)
  const [applyError, setApplyError] = useState<string | null>(null)
  const [applyResults, setApplyResults] = useState<ApplyActionResult[]>([])

  // ── Step 1 — run capture (dry_run=true, duration=60) ─────────────────────
  const runCapture = async () => {
    setCaptureError(null)
    setCaptureResult(null)
    try {
      const args: Record<string, unknown> = {
        genre,
        dry_run: true,
        duration: 60,
      }
      if (masterFilePath.trim() !== '') {
        args['master_file_path'] = masterFilePath.trim()
      }
      const res = await mcpClient.callTool({ name: 'auto_setup_mix', params: args })
      if (!res.success) {
        setCaptureError(res.error ?? 'Capture failed')
        return
      }
      const data = res.data as AutoSetupResult
      setCaptureResult(data)
      // Pre-check all actions
      setCheckedActions(new Set(data.setup_actions.map((_, i) => i)))
      // Auto-advance to Stems
      setStep(2)
    } catch (e) {
      setCaptureError(e instanceof Error ? e.message : 'Capture failed')
    }
  }

  useEffect(() => {
    if (step === 1) {
      void runCapture()
    }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Step 3 — Attribution auto-advances to Preview ─────────────────────────
  // No async work needed; attribution step just displays data.
  // Auto-advance is triggered when user clicks Next from step 2.

  // ── Step 5 — apply ────────────────────────────────────────────────────────
  const runApply = async () => {
    if (!captureResult) return
    if (dryRun) return  // Dry run — nothing to call
    setApplyLoading(true)
    setApplyError(null)
    setApplyResults([])
    try {
      const selectedActions = captureResult.setup_actions.filter((_, i) => checkedActions.has(i))
      const args: Record<string, unknown> = {
        genre,
        dry_run: false,
        duration: 60,
        selected_actions: selectedActions,
      }
      if (masterFilePath.trim() !== '') {
        args['master_file_path'] = masterFilePath.trim()
      }
      const res = await mcpClient.callTool({ name: 'auto_setup_mix', params: args })
      if (!res.success) {
        setApplyError(res.error ?? 'Apply failed')
        return
      }
      const resultData = res.data as { results?: ApplyActionResult[] }
      const resultList: ApplyActionResult[] = resultData.results ?? selectedActions.map(a => ({
        ...a,
        status: 'applied' as const,
      }))
      setApplyResults(resultList)
    } catch (e) {
      setApplyError(e instanceof Error ? e.message : 'Apply failed')
    } finally {
      setApplyLoading(false)
    }
  }

  useEffect(() => {
    if (step === 5) {
      void runApply()
    }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Step definitions ──────────────────────────────────────────────────────
  const steps: WorkflowStep[] = STEP_LABELS.map((label, i) => ({
    label,
    status: i < step ? 'done' : i === step ? 'active' : 'pending',
  }))

  // ── Navigation ────────────────────────────────────────────────────────────
  // Back: only from steps 2, 3, 4 (not from auto-running or apply)
  const showBack = step === 2 || step === 3 || step === 4
  // Next: shown on steps 2, 3, 4
  const showNext = step === 2 || step === 3 || step === 4

  const handleBack = () => {
    if (step === 2) setStep(0)        // Stems → Config (re-configure without re-capture)
    else if (step === 3) setStep(2)   // Attribution → Stems
    else if (step === 4) setStep(3)   // Preview → Attribution
  }

  const handleNext = () => {
    if (step === 2) setStep(3)        // Stems → Attribution
    else if (step === 3) setStep(4)   // Attribution → Preview
    else if (step === 4) setStep(5)   // Preview → Apply
  }

  const nextLabel =
    step === 4 ? (dryRun ? 'Preview Apply →' : 'Apply Now →') :
    step === 3 ? 'Review Actions →' :
    'View Attribution →'

  const nextDisabled = step === 4 && checkedActions.size === 0

  // ── Toggle action checkbox ────────────────────────────────────────────────
  const handleToggleAction = (index: number) => {
    setCheckedActions(prev => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <WorkflowShell
      title="Auto Setup Mix"
      icon="◈"
      steps={steps}
      currentStep={step}
      onBack={showBack ? handleBack : undefined}
      onNext={showNext ? handleNext : undefined}
      nextLabel={nextLabel}
      nextDisabled={nextDisabled}
      isLoading={
        (step === 1 && !captureError) ||
        (step === 5 && applyLoading)
      }
      onClose={onClose}
    >
      {step === 0 && (
        <ConfigStep
          genre={genre}
          masterFilePath={masterFilePath}
          dryRun={dryRun}
          onGenreChange={setGenre}
          onMasterFilePathChange={setMasterFilePath}
          onDryRunChange={setDryRun}
          onNext={() => setStep(1)}
        />
      )}

      {step === 1 && (
        <CaptureStep
          error={captureError}
          onRetry={() => setStep(0)}
        />
      )}

      {step === 2 && captureResult && (
        <StemsStep stems={captureResult.stems} />
      )}

      {step === 3 && captureResult && (
        <AttributionStep attribution={captureResult.attribution} />
      )}

      {step === 4 && captureResult && (
        <PreviewStep
          actions={captureResult.setup_actions}
          checked={checkedActions}
          onToggle={handleToggleAction}
        />
      )}

      {step === 5 && (
        <ApplyStep
          dryRun={dryRun}
          loading={applyLoading}
          error={applyError}
          results={applyResults}
          summary={captureResult?.summary}
          onClose={onClose}
        />
      )}
    </WorkflowShell>
  )
}
