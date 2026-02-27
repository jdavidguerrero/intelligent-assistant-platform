/**
 * AuditWorkflow — 4-step Session Intelligence audit workflow.
 *
 * Steps:
 *   0 Config   — genre preset picker (opt-in) + force_refresh toggle
 *   1 Auditing — auto-runs audit, shows loading spinner
 *   2 Findings — 3-tab panel (Universal / Pattern / Genre) with findings
 *   3 Apply    — apply selected fixes + save session patterns
 */

import React, { useState, useEffect } from 'react'
import { WorkflowShell } from './WorkflowShell'
import type { WorkflowStep } from './WorkflowShell'
import { mcpClient } from '../../services/mcpClient'
import type { AuditReport, AuditFinding } from '../../services/mcpClient'
import { useWorkflowStore } from '../../store/workflowStore'
import { useAuditStore } from '../../store/auditStore'
import { GenrePresetPicker } from '../GenrePresetPicker'
import { PatternInsights } from '../PatternInsights'

// ── Shared helpers ─────────────────────────────────────────────────────────

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

// ── STEP 0: Config ─────────────────────────────────────────────────────────

interface ConfigStepProps {
  genrePreset: string
  forceRefresh: boolean
  onGenreChange: (v: string) => void
  onForceChange: (v: boolean) => void
  onStart: () => void
}

function ConfigStep({ genrePreset, forceRefresh, onGenreChange, onForceChange, onStart }: ConfigStepProps) {
  return (
    <div className="p-4 flex flex-col gap-4">
      <div>
        <SectionLabel>Genre Preset (Layer 3)</SectionLabel>
        <GenrePresetPicker value={genrePreset} onChange={onGenreChange} />
      </div>

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={forceRefresh}
            onChange={e => onForceChange(e.target.checked)}
            className="accent-push-orange"
          />
          <span className="text-[10px] text-push-text">Force refresh (bypass session cache)</span>
        </label>
      </div>

      <div className="bg-push-surface border border-push-border rounded-[3px] p-3">
        <p className="text-[10px] text-push-muted leading-relaxed">
          <span className="text-push-orange">Layer 1</span> — Universal checks (EQ, HP filter, compression)<br/>
          <span className="text-push-orange">Layer 2</span> — Your personal patterns (needs ≥3 saved sessions)<br/>
          <span className="text-push-orange">Layer 3</span> — Genre style suggestions (opt-in above)
        </p>
      </div>

      {/* Pattern history preview */}
      <div>
        <SectionLabel>Your Pattern History</SectionLabel>
        <PatternInsights compact />
      </div>

      <button
        onClick={onStart}
        className="self-start px-4 py-1.5 rounded-[3px] border border-push-orange text-push-orange
                   text-[10px] uppercase tracking-[0.06em]
                   hover:bg-push-orange hover:text-push-bg
                   transition-colors"
      >
        Run Audit →
      </button>
    </div>
  )
}

// ── STEP 2: Findings ────────────────────────────────────────────────────────

type LayerFilter = 'all' | 'universal' | 'pattern' | 'genre'
type SeverityOrder = Record<string, number>

const SEVERITY_ORDER: SeverityOrder = { critical: 0, warning: 1, info: 2, suggestion: 3 }

function severityColor(severity: string): string {
  switch (severity) {
    case 'critical':   return 'text-push-red border-push-red'
    case 'warning':    return 'text-push-yellow border-push-yellow'
    case 'suggestion': return 'text-push-orange border-push-orange'
    default:           return 'text-push-muted border-push-border'
  }
}

function CountBadge({ count, color }: { count: number; color: string }) {
  if (count === 0) return null
  return (
    <span className={`px-1 py-0.5 rounded-[2px] border text-[8px] font-mono ml-1 ${color}`}>
      {count}
    </span>
  )
}

interface FindingCardProps {
  finding: AuditFinding
  selected: boolean
  onToggle: () => void
}

function FindingCard({ finding, selected, onToggle }: FindingCardProps) {
  const colorClass = severityColor(finding.severity)
  const hasfix = finding.fix_action !== null

  return (
    <div
      className={`
        bg-push-surface border rounded-[3px] p-3 flex flex-col gap-2
        ${selected ? 'border-push-orange' : 'border-push-border'}
      `}
    >
      {/* Header row */}
      <div className="flex items-center gap-2">
        <span className="text-[12px] leading-none">{finding.icon}</span>
        <span className={`text-[9px] uppercase tracking-[0.06em] font-bold border px-1.5 py-0.5 rounded-[2px] ${colorClass}`}>
          {finding.severity}
        </span>
        <span className="text-[9px] text-push-muted truncate flex-1">{finding.channel_name}</span>
        <span className="text-[8px] text-push-muted font-mono">{Math.round(finding.confidence * 100)}%</span>
      </div>

      {/* Message */}
      <p className="text-[11px] text-push-text leading-relaxed">{finding.message}</p>
      <p className="text-[10px] text-push-muted leading-relaxed">{finding.reason}</p>

      {/* Device name */}
      {finding.device_name && (
        <span className="text-[9px] text-push-orange">{finding.device_name}</span>
      )}

      {/* Fix toggle */}
      {hasfix && (
        <label className="flex items-center gap-2 cursor-pointer mt-1">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="accent-push-orange"
          />
          <span className="text-[9px] text-push-text">Include in Apply</span>
        </label>
      )}
    </div>
  )
}

interface FindingsStepProps {
  report: AuditReport
  selectedFixes: Set<number>
  onToggleFix: (index: number) => void
}

function FindingsStep({ report, selectedFixes, onToggleFix }: FindingsStepProps) {
  const [layerFilter, setLayerFilter] = useState<LayerFilter>('all')

  const filtered = report.findings
    .map((f, i) => ({ f, i }))
    .filter(({ f }) => layerFilter === 'all' || f.layer === layerFilter)
    .sort((a, b) => (SEVERITY_ORDER[a.f.severity] ?? 9) - (SEVERITY_ORDER[b.f.severity] ?? 9))

  const uCount = report.findings.filter(f => f.layer === 'universal').length
  const pCount = report.findings.filter(f => f.layer === 'pattern').length
  const gCount = report.findings.filter(f => f.layer === 'genre').length

  const tabClass = (active: boolean) => `
    px-3 py-1 text-[9px] uppercase tracking-[0.06em] rounded-[3px] border transition-colors
    ${active
      ? 'border-push-orange text-push-orange bg-push-orange/10'
      : 'border-transparent text-push-muted hover:text-push-text'}
  `

  return (
    <div className="p-4 flex flex-col gap-3">
      {/* Summary row */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[10px] text-push-red">❌ {report.critical_count}</span>
        <span className="text-[10px] text-push-yellow">⚠️ {report.warning_count}</span>
        <span className="text-[10px] text-push-muted">ℹ️ {report.info_count}</span>
        <span className="text-[10px] text-push-orange">💡 {report.suggestion_count}</span>
        <span className="text-[9px] text-push-muted ml-auto">
          {report.session_map.total_channels} channels mapped
        </span>
      </div>

      {/* Layer filter tabs */}
      <div className="flex gap-1 flex-wrap">
        <button className={tabClass(layerFilter === 'all')} onClick={() => setLayerFilter('all')}>
          All ({report.findings.length})
        </button>
        <button className={tabClass(layerFilter === 'universal')} onClick={() => setLayerFilter('universal')}>
          Universal
          <CountBadge count={uCount} color="text-push-red border-push-red" />
        </button>
        <button className={tabClass(layerFilter === 'pattern')} onClick={() => setLayerFilter('pattern')}>
          Pattern
          <CountBadge count={pCount} color="text-push-yellow border-push-yellow" />
        </button>
        <button className={tabClass(layerFilter === 'genre')} onClick={() => setLayerFilter('genre')}>
          Genre
          <CountBadge count={gCount} color="text-push-orange border-push-orange" />
        </button>
      </div>

      {/* Findings list */}
      {filtered.length === 0 ? (
        <div className="bg-push-surface border border-push-green rounded-[3px] p-3">
          <span className="text-[11px] text-push-green">
            {layerFilter === 'pattern'
              ? 'No pattern anomalies detected (or fewer than 3 sessions saved)'
              : layerFilter === 'genre'
              ? 'No genre-specific suggestions (no preset selected?)'
              : 'No findings — mix looks great ✓'}
          </span>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map(({ f, i }) => (
            <FindingCard
              key={i}
              finding={f}
              selected={selectedFixes.has(i)}
              onToggle={() => onToggleFix(i)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── STEP 3: Apply ───────────────────────────────────────────────────────────

type FixStatus = 'pending' | 'loading' | 'success' | 'error'

interface ApplyStepProps {
  report: AuditReport
  selectedFixes: Set<number>
  fixStatus: Record<number, FixStatus>
  fixErrors: Record<number, string>
  saveStatus: 'idle' | 'saving' | 'saved' | 'error'
  saveError: string | null
  onApplyFix: (index: number) => void
  onApplyAll: () => void
  onSavePatterns: () => void
}

function ApplyStep({
  report, selectedFixes, fixStatus, fixErrors,
  saveStatus, saveError, onApplyFix, onApplyAll, onSavePatterns,
}: ApplyStepProps) {
  const fixableFindings = report.findings
    .map((f, i) => ({ f, i }))
    .filter(({ f }) => f.fix_action !== null)

  const selectedFixable = fixableFindings.filter(({ i }) => selectedFixes.has(i))
  const appliedCount = Object.values(fixStatus).filter(s => s === 'success').length
  const errorCount   = Object.values(fixStatus).filter(s => s === 'error').length

  return (
    <div className="p-4 flex flex-col gap-4">

      {/* Save patterns section */}
      <div className="bg-push-surface border border-push-border rounded-[3px] p-3 flex flex-col gap-2">
        <SectionLabel>Save Session as Pattern Reference</SectionLabel>
        <p className="text-[10px] text-push-muted leading-relaxed">
          Save this session to your pattern history. Layer 2 activates after 3+ saved sessions.
        </p>
        {saveStatus === 'saved' && (
          <span className="text-[10px] text-push-green">✓ Session patterns saved</span>
        )}
        {saveStatus === 'error' && saveError && (
          <span className="text-[10px] text-push-red">{saveError}</span>
        )}
        <button
          onClick={onSavePatterns}
          disabled={saveStatus === 'saving' || saveStatus === 'saved'}
          className="self-start px-3 py-1 rounded-[3px] border border-push-border text-push-muted
                     text-[10px] uppercase tracking-[0.06em]
                     hover:border-push-text hover:text-push-text
                     disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {saveStatus === 'saving' ? '…' : saveStatus === 'saved' ? '✓ Saved' : 'Save Patterns'}
        </button>

        {/* Pattern insights after saving */}
        {saveStatus === 'saved' && (
          <div className="mt-2">
            <SectionLabel>Updated Pattern History</SectionLabel>
            <PatternInsights compact />
          </div>
        )}
      </div>

      {/* Apply fixes section */}
      {fixableFindings.length === 0 ? (
        <div className="bg-push-surface border border-push-border rounded-[3px] p-3">
          <span className="text-[11px] text-push-muted">No auto-fixable findings in this audit.</span>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <SectionLabel>Apply Fixes ({selectedFixable.length} selected)</SectionLabel>
            <div className="flex gap-2">
              {appliedCount > 0 && (
                <span className="text-[9px] text-push-green">✓ {appliedCount} applied</span>
              )}
              {errorCount > 0 && (
                <span className="text-[9px] text-push-red">✗ {errorCount} failed</span>
              )}
            </div>
          </div>

          {selectedFixable.length > 1 && (
            <button
              onClick={onApplyAll}
              disabled={Object.values(fixStatus).some(s => s === 'loading')}
              className="self-start px-3 py-1 rounded-[3px] border border-push-orange text-push-orange
                         text-[10px] uppercase tracking-[0.06em]
                         hover:bg-push-orange hover:text-push-bg
                         disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Apply All Selected ({selectedFixable.length})
            </button>
          )}

          <div className="flex flex-col gap-2">
            {fixableFindings.map(({ f, i }) => {
              const status = fixStatus[i] ?? 'pending'
              const err = fixErrors[i]
              const isSelected = selectedFixes.has(i)

              return (
                <div
                  key={i}
                  className={`
                    bg-push-surface border rounded-[3px] p-3 flex flex-col gap-2
                    ${isSelected ? 'border-push-border' : 'border-push-border opacity-50'}
                  `}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[11px]">{f.icon}</span>
                    <span className="text-[10px] text-push-text flex-1 truncate">
                      {f.channel_name} — {f.message}
                    </span>
                    {status === 'success' && (
                      <span className="text-[9px] text-push-green uppercase">✓</span>
                    )}
                    {status === 'error' && (
                      <span className="text-[9px] text-push-red uppercase">✗</span>
                    )}
                    {status === 'loading' && (
                      <span className="text-[9px] text-push-muted animate-pulse">…</span>
                    )}
                  </div>

                  {f.fix_action && (
                    <div className="flex gap-2 bg-push-elevated rounded-[2px] px-2 py-1">
                      <span className="text-[9px] text-push-orange font-mono truncate">
                        {f.fix_action.lom_path}
                      </span>
                      <span className="text-[9px] text-push-muted">·</span>
                      <span className="text-[9px] text-push-text font-mono">{f.fix_action.property} = {String(f.fix_action.value)}</span>
                    </div>
                  )}

                  {err && <p className="text-[10px] text-push-red">{err}</p>}

                  <button
                    onClick={() => onApplyFix(i)}
                    disabled={!isSelected || status === 'loading' || status === 'success'}
                    className="self-start px-3 py-1 rounded-[3px] border border-push-orange text-push-orange
                               text-[10px] uppercase tracking-[0.06em]
                               hover:bg-push-orange hover:text-push-bg
                               disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    {status === 'loading' ? '…' : status === 'success' ? '✓ Applied' : 'Apply Fix'}
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main component ──────────────────────────────────────────────────────────

export function AuditWorkflow() {
  const { setWorkflow } = useWorkflowStore()
  const setFindings = useAuditStore((s) => s.setFindings)

  const [step, setStep] = useState(0)
  const [genrePreset, setGenrePreset] = useState('')
  const [forceRefresh, setForceRefresh] = useState(false)

  const [auditError, setAuditError] = useState<string | null>(null)
  const [report, setReport] = useState<AuditReport | null>(null)

  const [selectedFixes, setSelectedFixes] = useState<Set<number>>(new Set())

  const [fixStatus, setFixStatus] = useState<Record<number, FixStatus>>({})
  const [fixErrors, setFixErrors] = useState<Record<number, string>>({})

  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  // ── Step 1: auto-run audit ─────────────────────────────────────────────────
  const runAudit = async () => {
    setAuditError(null)
    try {
      const result = await mcpClient.auditSession({
        genre_preset: genrePreset || null,
        force_refresh: forceRefresh,
      })
      setReport(result)
      setFindings(result.findings)
      // Pre-select all fixable findings
      const fixableIndices = result.findings
        .map((f, i) => ({ f, i }))
        .filter(({ f }) => f.fix_action !== null)
        .map(({ i }) => i)
      setSelectedFixes(new Set(fixableIndices))
      setStep(2)
    } catch (e) {
      setAuditError(e instanceof Error ? e.message : 'Audit failed')
    }
  }

  useEffect(() => {
    if (step === 1) {
      void runAudit()
    }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Fix handlers ──────────────────────────────────────────────────────────
  const handleApplyFix = async (index: number) => {
    const finding = report?.findings[index]
    if (!finding?.fix_action) return

    setFixStatus(prev => ({ ...prev, [index]: 'loading' }))
    try {
      await mcpClient.applyFix({
        lom_path: finding.fix_action.lom_path,
        lom_id: finding.fix_action.lom_id,
        property: finding.fix_action.property,
        value: finding.fix_action.value,
        description: `audit_fix: ${finding.rule_id} on ${finding.channel_name}`,
      })
      setFixStatus(prev => ({ ...prev, [index]: 'success' }))
    } catch (e) {
      setFixStatus(prev => ({ ...prev, [index]: 'error' }))
      setFixErrors(prev => ({
        ...prev,
        [index]: e instanceof Error ? e.message : 'Fix failed',
      }))
    }
  }

  const handleApplyAll = async () => {
    if (!report) return
    const pending = report.findings
      .map((f, i) => ({ f, i }))
      .filter(({ f, i }) => f.fix_action !== null && selectedFixes.has(i) && !fixStatus[i])
    for (const { i } of pending) {
      await handleApplyFix(i)
    }
  }

  const handleSavePatterns = async () => {
    setSaveStatus('saving')
    setSaveError(null)
    try {
      await mcpClient.savePatterns()
      setSaveStatus('saved')
    } catch (e) {
      setSaveStatus('error')
      setSaveError(e instanceof Error ? e.message : 'Save failed')
    }
  }

  const toggleFix = (index: number) => {
    setSelectedFixes(prev => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  // ── Step definitions ──────────────────────────────────────────────────────
  const STEP_LABELS = ['Config', 'Audit', 'Findings', 'Apply']
  const steps: WorkflowStep[] = STEP_LABELS.map((label, i) => ({
    label,
    status: i < step ? 'done' : i === step ? 'active' : 'pending',
  }))

  const showBack = step === 2 || step === 3
  const showNext = step === 2

  const handleBack = () => {
    if (step === 2) setStep(0)
    else if (step === 3) setStep(2)
  }

  const handleNext = () => {
    if (step === 2) setStep(3)
  }

  return (
    <WorkflowShell
      title="Session Audit"
      icon="⊛"
      steps={steps}
      currentStep={step}
      onBack={showBack ? handleBack : undefined}
      onNext={showNext ? handleNext : undefined}
      nextLabel="Apply Fixes →"
      isLoading={step === 1 && !auditError}
      onClose={() => setWorkflow(null)}
    >
      {step === 0 && (
        <ConfigStep
          genrePreset={genrePreset}
          forceRefresh={forceRefresh}
          onGenreChange={setGenrePreset}
          onForceChange={setForceRefresh}
          onStart={() => setStep(1)}
        />
      )}

      {step === 1 && (
        auditError ? (
          <div className="p-4 flex flex-col gap-2">
            <span className="text-[10px] text-push-red">{auditError}</span>
            <button
              onClick={() => setStep(0)}
              className="self-start px-3 py-1 rounded-[3px] border border-push-orange text-push-orange
                         text-[10px] uppercase tracking-[0.06em]
                         hover:bg-push-orange hover:text-push-bg transition-colors"
            >
              ← Back
            </button>
          </div>
        ) : (
          <LoadingSpinner label="Running 3-layer audit…" />
        )
      )}

      {step === 2 && report && (
        <FindingsStep
          report={report}
          selectedFixes={selectedFixes}
          onToggleFix={toggleFix}
        />
      )}

      {step === 3 && report && (
        <ApplyStep
          report={report}
          selectedFixes={selectedFixes}
          fixStatus={fixStatus}
          fixErrors={fixErrors}
          saveStatus={saveStatus}
          saveError={saveError}
          onApplyFix={(i) => { void handleApplyFix(i) }}
          onApplyAll={() => { void handleApplyAll() }}
          onSavePatterns={() => { void handleSavePatterns() }}
        />
      )}
    </WorkflowShell>
  )
}
