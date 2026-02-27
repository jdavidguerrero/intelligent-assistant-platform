/**
 * ReferenceWorkflow — 5-step A/B comparison against commercial reference tracks.
 *
 * Steps:
 *   0 Tracks      — your track path + 1–5 reference paths + genre
 *   1 Compare     — call compareReference → auto-advance to Dimensions on success
 *   2 Dimensions  — overall similarity score + per-dimension score bars
 *   3 Deltas      — sorted actionable deltas + optional band deltas table
 *   4 Done        — LUFS delta summary + re-compare or close
 */

import React, { useState, useEffect } from 'react'
import { WorkflowShell } from './WorkflowShell'
import type { WorkflowStep } from './WorkflowShell'
import { mcpClient } from '../../services/mcpClient'
import type { ComparisonReport } from '../../services/mcpClient'
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

// ── Step 0: Tracks ────────────────────────────────────────────────────────────

interface TracksStepProps {
  myTrack: string
  refPaths: string[]
  genre: string
  onMyTrackChange: (v: string) => void
  onRefPathChange: (index: number, v: string) => void
  onAddRef: () => void
  onRemoveRef: (index: number) => void
  onGenreChange: (v: string) => void
  onNext: () => void
}

function TracksStep({
  myTrack, refPaths, genre,
  onMyTrackChange, onRefPathChange, onAddRef, onRemoveRef,
  onGenreChange, onNext,
}: TracksStepProps) {
  const canAddMore = refPaths.length < 5
  const anyEmpty = myTrack.trim() === '' || refPaths.some(p => p.trim() === '')

  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Your track */}
      <div>
        <SectionLabel>Your Track</SectionLabel>
        <input
          type="text"
          className={inputClass}
          value={myTrack}
          onChange={e => onMyTrackChange(e.target.value)}
          placeholder="/path/to/your_mix.wav"
          spellCheck={false}
        />
      </div>

      {/* Reference tracks */}
      <div>
        <SectionLabel>Reference Tracks</SectionLabel>
        <div className="flex flex-col gap-2">
          {refPaths.map((path, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                type="text"
                className={inputClass}
                value={path}
                onChange={e => onRefPathChange(i, e.target.value)}
                placeholder={`/path/to/reference_${i + 1}.wav`}
                spellCheck={false}
              />
              {refPaths.length > 1 && (
                <button
                  onClick={() => onRemoveRef(i)}
                  className="flex-shrink-0 text-push-muted hover:text-push-red text-[10px] transition-colors px-1"
                  title="Remove reference"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>

        {canAddMore && (
          <button
            onClick={onAddRef}
            className="mt-2 text-[10px] text-push-blue hover:text-push-text uppercase tracking-[0.06em] transition-colors"
          >
            + Add Reference
          </button>
        )}
      </div>

      {/* Genre */}
      <div>
        <SectionLabel>Genre</SectionLabel>
        <select className={selectClass} value={genre} onChange={e => onGenreChange(e.target.value)}>
          {SUPPORTED_GENRES.map(g => <option key={g} value={g}>{g}</option>)}
        </select>
      </div>

      <p className="text-[9px] text-push-muted leading-relaxed">
        Paths are on the server filesystem — use bounced WAV or AIFF files.
      </p>

      <button
        onClick={onNext}
        disabled={anyEmpty}
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

// ── Step 1: Compare (auto-runs) ───────────────────────────────────────────────

interface CompareStepProps {
  error: string | null
  onBack: () => void
}

function CompareStep({ error, onBack }: CompareStepProps) {
  if (error) {
    return (
      <div className="p-4 flex flex-col gap-2">
        <span className="text-[10px] text-push-red">{error}</span>
        <button
          onClick={onBack}
          className="self-start px-3 py-1 rounded-[3px] border border-push-orange text-push-orange
                     text-[10px] uppercase tracking-[0.06em]
                     hover:bg-push-orange hover:text-push-bg transition-colors"
        >
          ← Back
        </button>
      </div>
    )
  }
  return <LoadingSpinner label="Analyzing and comparing tracks…" />
}

// ── Step 2: Dimensions ────────────────────────────────────────────────────────

interface DimensionsStepProps {
  comparison: ComparisonReport
}

function similarityColor(score: number): string {
  if (score >= 70) return 'text-push-green'
  if (score >= 50) return 'text-push-yellow'
  return 'text-push-red'
}

function DimensionsStep({ comparison }: DimensionsStepProps) {
  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Overall similarity */}
      <div className="flex flex-col items-center gap-1 py-3">
        <span className={`text-4xl font-bold font-mono ${similarityColor(comparison.overall_similarity)}`}>
          {Math.round(comparison.overall_similarity)}%
        </span>
        <span className="text-[10px] text-push-muted">Overall Similarity</span>
      </div>

      {/* Dimensions grid */}
      <div>
        <SectionLabel>Dimensions</SectionLabel>
        <div className="grid grid-cols-2 gap-2">
          {comparison.dimensions.map((dim, i) => (
            <div
              key={i}
              className="bg-push-surface border border-push-border rounded-[3px] p-2"
            >
              <span className="text-[9px] uppercase tracking-[0.08em] text-push-muted block mb-1">
                {dim.name}
              </span>

              {/* Score bar */}
              <div className="relative h-1.5 bg-push-border rounded-full mb-1">
                <div
                  className="absolute left-0 top-0 h-full bg-push-orange rounded-full"
                  style={{ width: `${Math.min(100, Math.max(0, dim.score))}%` }}
                />
              </div>

              <div className="flex items-center justify-between">
                <div className="flex flex-col gap-0.5">
                  {dim.track_value !== null && dim.ref_value !== null && (
                    <span className="text-[8px] text-push-muted font-mono">
                      {dim.track_value.toFixed(1)} vs {dim.ref_value.toFixed(1)}{dim.unit ? ` ${dim.unit}` : ''}
                    </span>
                  )}
                </div>
                <span className="text-[11px] font-mono text-push-text">
                  {Math.round(dim.score)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Step 3: Deltas ────────────────────────────────────────────────────────────

interface DeltasStepProps {
  comparison: ComparisonReport
}

function directionBadge(direction: string): { label: string; cls: string } {
  const d = direction.toLowerCase()
  if (d === 'increase') return { label: '↑ Increase', cls: 'text-push-blue border-push-blue' }
  if (d === 'decrease') return { label: '↓ Decrease', cls: 'text-push-orange border-push-orange' }
  return { label: '→ Adjust', cls: 'text-push-yellow border-push-yellow' }
}

function priorityBadge(priority: number): { label: string; cls: string } {
  if (priority === 1) return { label: 'HIGH', cls: 'text-push-red border-push-red' }
  if (priority === 2) return { label: 'MED', cls: 'text-push-yellow border-push-yellow' }
  return { label: 'LOW', cls: 'text-push-green border-push-green' }
}

function bandDeltaColor(delta: number): string {
  const abs = Math.abs(delta)
  if (abs > 3) return 'text-push-red'
  if (abs > 1) return 'text-push-yellow'
  return 'text-push-green'
}

function DeltasStep({ comparison }: DeltasStepProps) {
  const sortedDeltas = [...comparison.deltas].sort((a, b) => a.priority - b.priority)

  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Deltas */}
      <div>
        <SectionLabel>Top Gaps ({sortedDeltas.length})</SectionLabel>
        {sortedDeltas.length === 0 ? (
          <div className="bg-push-surface border border-push-green rounded-[3px] p-3">
            <span className="text-[11px] text-push-green">No significant gaps detected ✓</span>
          </div>
        ) : (
          <div className="flex flex-col">
            {sortedDeltas.map((delta, i) => {
              const dir = directionBadge(delta.direction)
              const pri = priorityBadge(delta.priority)
              return (
                <div
                  key={i}
                  className="bg-push-surface border border-push-border rounded-[3px] p-3 mb-2"
                >
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className={`text-[9px] px-1.5 py-0.5 border rounded-[2px] flex-shrink-0 ${dir.cls}`}
                      >
                        {dir.label}
                      </span>
                      <span className="text-[11px] text-push-text">
                        {delta.dimension}
                      </span>
                      <span className="text-[10px] font-mono text-push-muted">
                        {delta.magnitude.toFixed(1)}{delta.unit ? ` ${delta.unit}` : ''}
                      </span>
                    </div>
                    <span
                      className={`text-[8px] px-1.5 py-0.5 border rounded-[2px] flex-shrink-0 uppercase tracking-[0.06em] ${pri.cls}`}
                    >
                      {pri.label}
                    </span>
                  </div>
                  <p className="text-[10px] text-push-muted leading-relaxed">
                    {delta.recommendation}
                  </p>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Band deltas table */}
      {comparison.band_deltas && comparison.band_deltas.length > 0 && (
        <div>
          <SectionLabel>Band Deltas</SectionLabel>
          <div className="bg-push-surface border border-push-border rounded-[3px] overflow-hidden">
            {/* Header */}
            <div className="grid grid-cols-4 gap-0 border-b border-push-border px-2 py-1">
              <span className="text-[8px] uppercase tracking-[0.08em] text-push-muted">Band</span>
              <span className="text-[8px] uppercase tracking-[0.08em] text-push-muted text-right">Your Mix</span>
              <span className="text-[8px] uppercase tracking-[0.08em] text-push-muted text-right">Reference</span>
              <span className="text-[8px] uppercase tracking-[0.08em] text-push-muted text-right">Delta</span>
            </div>
            {/* Rows */}
            {comparison.band_deltas.map((row, i) => (
              <div
                key={i}
                className="grid grid-cols-4 gap-0 px-2 py-1 border-b border-push-border last:border-b-0"
              >
                <span className="text-[9px] text-push-muted uppercase">{row.band}</span>
                <span className="text-[9px] font-mono text-push-text text-right">
                  {row.track_db.toFixed(1)}
                </span>
                <span className="text-[9px] font-mono text-push-muted text-right">
                  {row.reference_db.toFixed(1)}
                </span>
                <span className={`text-[9px] font-mono text-right ${bandDeltaColor(row.delta_db)}`}>
                  {row.delta_db > 0 ? '+' : ''}{row.delta_db.toFixed(1)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Step 4: Done ──────────────────────────────────────────────────────────────

interface DoneStepProps {
  comparison: ComparisonReport
  onReCompare: () => void
  onClose: () => void
}

function DoneStep({ comparison, onReCompare, onClose }: DoneStepProps) {
  const { lufs_delta, lufs_normalization_db, num_references } = comparison
  const absLufs = Math.abs(lufs_delta)
  const direction = lufs_delta < 0 ? 'quieter than' : 'louder than'

  return (
    <div className="p-4 flex flex-col gap-4">
      <SectionLabel>Analysis Complete</SectionLabel>

      <div className="bg-push-surface border border-push-border rounded-[3px] p-3 flex flex-col gap-3">
        {/* LUFS delta explanation */}
        <div className="flex flex-col gap-1">
          <span className="text-[9px] uppercase tracking-[0.08em] text-push-muted">Loudness Delta</span>
          <span className="text-[11px] text-push-text leading-relaxed">
            Your mix is{' '}
            <span className="font-mono text-push-orange">{absLufs.toFixed(1)} dB</span>{' '}
            {direction} the reference after normalization.
          </span>
          {lufs_normalization_db !== 0 && (
            <span className="text-[10px] text-push-muted">
              Normalization applied: {lufs_normalization_db > 0 ? '+' : ''}{lufs_normalization_db.toFixed(1)} dB
            </span>
          )}
        </div>

        {/* References analyzed */}
        <div className="flex items-center justify-between">
          <span className="text-[9px] uppercase tracking-[0.08em] text-push-muted">References Analyzed</span>
          <span className="text-[12px] font-mono text-push-text">{num_references}</span>
        </div>

        {/* Overall similarity recap */}
        <div className="flex items-center justify-between">
          <span className="text-[9px] uppercase tracking-[0.08em] text-push-muted">Overall Similarity</span>
          <span className={`text-[12px] font-mono ${similarityColor(comparison.overall_similarity)}`}>
            {Math.round(comparison.overall_similarity)}%
          </span>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={onReCompare}
          className="flex-1 py-1.5 rounded-[3px] border border-push-orange text-push-orange
                     text-[10px] uppercase tracking-[0.06em]
                     hover:bg-push-orange hover:text-push-bg
                     transition-colors"
        >
          Re-Compare
        </button>
        <button
          onClick={onClose}
          className="flex-1 py-1.5 rounded-[3px] bg-push-orange text-push-bg
                     text-[10px] uppercase tracking-[0.06em] font-medium
                     hover:opacity-90 transition-opacity"
        >
          Done
        </button>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function ReferenceWorkflow() {
  const { setWorkflow } = useWorkflowStore()

  const [step, setStep] = useState(0)
  const [myTrack, setMyTrack] = useState('')
  const [refPaths, setRefPaths] = useState<string[]>([''])
  const [genre, setGenre] = useState(SUPPORTED_GENRES[0] ?? 'organic house')
  const [compareError, setCompareError] = useState<string | null>(null)
  const [comparison, setComparison] = useState<ComparisonReport | null>(null)

  // ── Reference path helpers ────────────────────────────────────────────────
  const handleRefPathChange = (index: number, value: string) => {
    setRefPaths(prev => prev.map((p, i) => (i === index ? value : p)))
  }

  const handleAddRef = () => {
    if (refPaths.length < 5) {
      setRefPaths(prev => [...prev, ''])
    }
  }

  const handleRemoveRef = (index: number) => {
    if (refPaths.length > 1) {
      setRefPaths(prev => prev.filter((_, i) => i !== index))
    }
  }

  // ── Step 1 — run comparison ───────────────────────────────────────────────
  const runComparison = async () => {
    setCompareError(null)
    const filtered = refPaths.filter(p => p.trim() !== '')
    try {
      const report = await mcpClient.compareReference({
        file_path: myTrack,
        reference_paths: filtered,
        genre,
      })
      setComparison(report)
      setStep(2)  // auto-advance to Dimensions
    } catch (e) {
      setCompareError(e instanceof Error ? e.message : 'Comparison failed')
    }
  }

  useEffect(() => {
    if (step === 1 && myTrack.trim() !== '') {
      void runComparison()
    }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Step definitions ──────────────────────────────────────────────────────
  const STEP_LABELS = ['Tracks', 'Compare', 'Dimensions', 'Deltas', 'Done']
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

  const nextLabel = step === 3 ? 'Fix & Re-compare →' : 'View Gaps →'

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <WorkflowShell
      title="Reference Compare"
      icon="⇄"
      steps={steps}
      currentStep={step}
      onBack={showBack ? handleBack : undefined}
      onNext={showNext ? handleNext : undefined}
      nextLabel={nextLabel}
      isLoading={step === 1 && !compareError}
      onClose={() => setWorkflow(null)}
    >
      {step === 0 && (
        <TracksStep
          myTrack={myTrack}
          refPaths={refPaths}
          genre={genre}
          onMyTrackChange={setMyTrack}
          onRefPathChange={handleRefPathChange}
          onAddRef={handleAddRef}
          onRemoveRef={handleRemoveRef}
          onGenreChange={setGenre}
          onNext={() => setStep(1)}
        />
      )}

      {step === 1 && (
        <CompareStep
          error={compareError}
          onBack={() => setStep(0)}
        />
      )}

      {step === 2 && comparison && (
        <DimensionsStep comparison={comparison} />
      )}

      {step === 3 && comparison && (
        <DeltasStep comparison={comparison} />
      )}

      {step === 4 && comparison && (
        <DoneStep
          comparison={comparison}
          onReCompare={() => setStep(0)}
          onClose={() => setWorkflow(null)}
        />
      )}
    </WorkflowShell>
  )
}
