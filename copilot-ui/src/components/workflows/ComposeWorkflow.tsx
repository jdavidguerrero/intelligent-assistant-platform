/**
 * ComposeWorkflow — 5-step guided composition assistant.
 *
 * Steps:
 *   0 Setup   — key / mood / genre / bars
 *   1 Chords  — suggest_chord_progression → display + store
 *   2 Bass    — generate_bassline → step sequencer display
 *   3 Drums   — generate_drum_pattern → 16-step grid display
 *   4 Insert  — push chords + drums into Ableton, then close
 */

import React, { useState, useEffect } from 'react'
import { WorkflowShell } from './WorkflowShell'
import type { WorkflowStep } from './WorkflowShell'
import { mcpClient } from '../../services/mcpClient'
import { SUPPORTED_GENRES } from '../../types/analysis'
import { useWorkflowStore } from '../../store/workflowStore'

// ── Local result shapes ──────────────────────────────────────────────────────

interface ChordResult {
  chords: string[]
  progression: string
  roman_analysis: string
  voicing_notes: string
  production_tips: string
}

interface MidiNote {
  note: string
  octave: number
  duration: string
  velocity: number
}

interface BassResult {
  pattern: string[]
  description: string
  midi_notes: MidiNote[]
  technique: string
}

interface DrumResult {
  patterns: Record<string, number[]>
  description: string
  groove_notes: string
}

type InsertStatus = 'pending' | 'loading' | 'success' | 'error'

// ── Helpers ──────────────────────────────────────────────────────────────────

function LoadingSpinner({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-8">
      <div
        className="w-6 h-6 rounded-full border-2 border-push-border border-t-push-orange animate-spin"
      />
      <span className="text-[10px] text-push-muted uppercase tracking-[0.08em]">{label}</span>
    </div>
  )
}

function ErrorMessage({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col gap-2 p-4">
      <span className="text-[10px] text-push-red">{message}</span>
      <button
        onClick={onRetry}
        className="self-start px-3 py-1 rounded-[3px] border border-push-orange text-push-orange
                   text-[10px] uppercase tracking-[0.06em] hover:bg-push-orange hover:text-push-bg
                   transition-colors"
      >
        Retry
      </button>
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

function InsertStatusBadge({ status }: { status: InsertStatus }) {
  if (status === 'pending') {
    return (
      <span className="px-2 py-0.5 rounded-[3px] border border-push-border text-push-muted text-[9px] uppercase tracking-[0.06em]">
        Pending
      </span>
    )
  }
  if (status === 'loading') {
    return (
      <span className="px-2 py-0.5 rounded-[3px] border border-push-border text-push-muted text-[9px] uppercase tracking-[0.06em] animate-pulse">
        Inserting…
      </span>
    )
  }
  if (status === 'success') {
    return (
      <span className="px-2 py-0.5 rounded-[3px] border border-push-green text-push-green text-[9px] uppercase tracking-[0.06em]">
        ✓ Inserted
      </span>
    )
  }
  return (
    <span className="px-2 py-0.5 rounded-[3px] border border-push-red text-push-red text-[9px] uppercase tracking-[0.06em]">
      ✗ Failed
    </span>
  )
}

// ── Step 0: Setup ─────────────────────────────────────────────────────────────

const KEYS = [
  'A minor', 'B minor', 'C minor', 'D minor', 'E minor', 'F minor', 'G minor',
  'A major', 'C major', 'D major', 'E major', 'F major', 'G major',
]
const MOODS = ['melancholic', 'uplifting', 'dark', 'euphoric', 'dreamy']
const BAR_OPTIONS = [4, 8, 16]

interface SetupStepProps {
  keyVal: string
  mood: string
  genre: string
  bars: number
  onKeyChange: (v: string) => void
  onMoodChange: (v: string) => void
  onGenreChange: (v: string) => void
  onBarsChange: (v: number) => void
}

function SetupStep({
  keyVal, mood, genre, bars,
  onKeyChange, onMoodChange, onGenreChange, onBarsChange,
}: SetupStepProps) {
  const selectClass = `
    w-full bg-push-elevated border border-push-border rounded-[3px]
    text-[11px] text-push-text px-2 py-1.5
    focus:outline-none focus:border-push-orange transition-colors
  `
  return (
    <div className="p-4 flex flex-col gap-3">
      <div>
        <SectionLabel>Key</SectionLabel>
        <select className={selectClass} value={keyVal} onChange={e => onKeyChange(e.target.value)}>
          {KEYS.map(k => <option key={k} value={k}>{k}</option>)}
        </select>
      </div>

      <div>
        <SectionLabel>Mood</SectionLabel>
        <select className={selectClass} value={mood} onChange={e => onMoodChange(e.target.value)}>
          {MOODS.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>

      <div>
        <SectionLabel>Genre</SectionLabel>
        <select className={selectClass} value={genre} onChange={e => onGenreChange(e.target.value)}>
          {SUPPORTED_GENRES.map(g => <option key={g} value={g}>{g}</option>)}
        </select>
      </div>

      <div>
        <SectionLabel>Bars</SectionLabel>
        <select className={selectClass} value={bars} onChange={e => onBarsChange(Number(e.target.value))}>
          {BAR_OPTIONS.map(b => <option key={b} value={b}>{b} bars</option>)}
        </select>
      </div>
    </div>
  )
}

// ── Step 1: Chords ────────────────────────────────────────────────────────────

interface ChordsStepProps {
  loading: boolean
  error: string | null
  result: ChordResult | null
  onRetry: () => void
}

function ChordsStep({ loading, error, result, onRetry }: ChordsStepProps) {
  if (loading) return <LoadingSpinner label="Generating chord progression…" />
  if (error) return <ErrorMessage message={error} onRetry={onRetry} />
  if (!result) return null

  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Chord badges */}
      <div>
        <SectionLabel>Progression</SectionLabel>
        <div className="flex flex-wrap gap-1.5">
          {result.chords.map((chord, i) => (
            <span
              key={i}
              className="px-2 py-1 bg-push-surface border border-push-orange text-push-orange
                         rounded-[3px] text-[11px] font-mono"
            >
              {chord}
            </span>
          ))}
        </div>
        <span className="text-[10px] text-push-muted mt-1 block">{result.roman_analysis}</span>
      </div>

      {/* Voicing notes */}
      <div>
        <SectionLabel>Voicing Notes</SectionLabel>
        <p className="text-[11px] text-push-text leading-relaxed">{result.voicing_notes}</p>
      </div>

      {/* Production tips */}
      <div>
        <SectionLabel>Production Tips</SectionLabel>
        <p className="text-[11px] text-push-muted leading-relaxed">{result.production_tips}</p>
      </div>
    </div>
  )
}

// ── Step 2: Bass ──────────────────────────────────────────────────────────────

interface BassStepProps {
  loading: boolean
  error: string | null
  result: BassResult | null
  onRetry: () => void
}

function BassStep({ loading, error, result, onRetry }: BassStepProps) {
  if (loading) return <LoadingSpinner label="Generating bassline…" />
  if (error) return <ErrorMessage message={error} onRetry={onRetry} />
  if (!result) return null

  // Show first 16 pattern steps as step-sequencer squares
  const steps = result.pattern.slice(0, 16)

  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Step sequencer display */}
      <div>
        <SectionLabel>Pattern (16 steps)</SectionLabel>
        <div className="flex gap-1 flex-wrap">
          {steps.map((step, i) => (
            <div
              key={i}
              title={`Step ${i + 1}: ${step}`}
              className="rounded-[2px] flex-shrink-0"
              style={{
                width: 14,
                height: 14,
                background: step !== '-' && step !== '0' && step !== ''
                  ? '#FF7700'
                  : '#2E2E2E',
              }}
            />
          ))}
          {/* Pad to 16 if shorter */}
          {Array.from({ length: Math.max(0, 16 - steps.length) }).map((_, i) => (
            <div
              key={`pad-${i}`}
              className="rounded-[2px] flex-shrink-0"
              style={{ width: 14, height: 14, background: '#2E2E2E' }}
            />
          ))}
        </div>
      </div>

      {/* Description */}
      <div>
        <SectionLabel>Description</SectionLabel>
        <p className="text-[11px] text-push-text leading-relaxed">{result.description}</p>
      </div>

      {/* Technique */}
      <div>
        <SectionLabel>Technique</SectionLabel>
        <p className="text-[11px] text-push-muted leading-relaxed">{result.technique}</p>
      </div>
    </div>
  )
}

// ── Step 3: Drums ─────────────────────────────────────────────────────────────

interface DrumsStepProps {
  loading: boolean
  error: string | null
  result: DrumResult | null
  onRetry: () => void
}

function DrumsStep({ loading, error, result, onRetry }: DrumsStepProps) {
  if (loading) return <LoadingSpinner label="Generating drum pattern…" />
  if (error) return <ErrorMessage message={error} onRetry={onRetry} />
  if (!result) return null

  const instruments = Object.keys(result.patterns)

  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Drum grid */}
      <div>
        <SectionLabel>16-Step Grid</SectionLabel>
        <div className="flex flex-col gap-1">
          {instruments.map(inst => {
            const hits = result.patterns[inst] ?? []
            return (
              <div key={inst} className="flex items-center gap-2">
                <span
                  className="text-[9px] text-push-muted uppercase tracking-[0.04em] flex-shrink-0"
                  style={{ width: 48 }}
                >
                  {inst.slice(0, 6)}
                </span>
                <div className="flex gap-0.5">
                  {Array.from({ length: 16 }).map((_, i) => (
                    <div
                      key={i}
                      className="rounded-[2px] flex-shrink-0"
                      style={{
                        width: 12,
                        height: 12,
                        background: hits[i] === 1 ? '#FF7700' : 'transparent',
                        border: hits[i] === 1 ? 'none' : '1px solid #2E2E2E',
                      }}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Description */}
      <div>
        <SectionLabel>Description</SectionLabel>
        <p className="text-[11px] text-push-text leading-relaxed">{result.description}</p>
      </div>

      {/* Groove notes */}
      <div>
        <SectionLabel>Groove Notes</SectionLabel>
        <p className="text-[11px] text-push-muted leading-relaxed">{result.groove_notes}</p>
      </div>
    </div>
  )
}

// ── Step 4: Insert ────────────────────────────────────────────────────────────

interface InsertStepProps {
  bars: number
  chordsData: ChordResult | null
  drumsData: DrumResult | null
  chordsStatus: InsertStatus
  drumsStatus: InsertStatus
  chordsError: string | null
  drumsError: string | null
  onInsertChords: () => void
  onInsertDrums: () => void
  onDone: () => void
}

function InsertStep({
  bars, chordsData, drumsData,
  chordsStatus, drumsStatus,
  chordsError, drumsError,
  onInsertChords, onInsertDrums, onDone,
}: InsertStepProps) {
  const bothAttempted =
    (chordsStatus === 'success' || chordsStatus === 'error') &&
    (drumsStatus === 'success' || drumsStatus === 'error')

  const btnClass = `
    px-3 py-1.5 rounded-[3px] border border-push-orange text-push-orange
    text-[10px] uppercase tracking-[0.06em]
    hover:bg-push-orange hover:text-push-bg
    disabled:opacity-40 disabled:cursor-not-allowed
    transition-colors
  `

  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Summary */}
      <div>
        <SectionLabel>What will be inserted</SectionLabel>
        <div className="flex flex-col gap-1 bg-push-surface border border-push-border rounded-[3px] p-3">
          <span className="text-[11px] text-push-text">
            Chord progression: {chordsData ? chordsData.chords.join(' → ') : '—'}
          </span>
          <span className="text-[11px] text-push-text">
            Bassline: {bars} bars
          </span>
          <span className="text-[11px] text-push-text">
            Drum pattern: {bars} bars
            {drumsData && ` (${Object.keys(drumsData.patterns).length} instruments)`}
          </span>
        </div>
      </div>

      {/* Insert chords */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <SectionLabel>Chords Track</SectionLabel>
          <InsertStatusBadge status={chordsStatus} />
        </div>
        <button
          className={btnClass}
          disabled={chordsStatus === 'loading' || chordsStatus === 'success'}
          onClick={onInsertChords}
        >
          Insert Chords to Ableton
        </button>
        {chordsError && (
          <p className="text-[10px] text-push-red mt-1">{chordsError}</p>
        )}
      </div>

      {/* Insert drums */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <SectionLabel>Drum Track</SectionLabel>
          <InsertStatusBadge status={drumsStatus} />
        </div>
        <button
          className={btnClass}
          disabled={drumsStatus === 'loading' || drumsStatus === 'success'}
          onClick={onInsertDrums}
        >
          Insert Drums to Ableton
        </button>
        {drumsError && (
          <p className="text-[10px] text-push-red mt-1">{drumsError}</p>
        )}
      </div>

      {/* Done */}
      {bothAttempted && (
        <button
          onClick={onDone}
          className="self-start px-4 py-1.5 rounded-[3px] bg-push-orange text-push-bg
                     text-[10px] uppercase tracking-[0.06em] font-medium transition-colors
                     hover:opacity-90"
        >
          Done
        </button>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function ComposeWorkflow() {
  const { setWorkflow } = useWorkflowStore()

  // Setup state
  const [step, setStep] = useState(0)
  const [keyVal, setKeyVal] = useState('A minor')
  const [mood, setMood] = useState('melancholic')
  const [genre, setGenre] = useState(SUPPORTED_GENRES[0] ?? 'organic house')
  const [bars, setBars] = useState(8)

  // Results
  const [chordsLoading, setChordsLoading] = useState(false)
  const [chordsError, setChordsError] = useState<string | null>(null)
  const [chordsData, setChordsData] = useState<ChordResult | null>(null)

  const [bassLoading, setBassLoading] = useState(false)
  const [bassError, setBassError] = useState<string | null>(null)
  const [bassData, setBassData] = useState<BassResult | null>(null)

  const [drumsLoading, setDrumsLoading] = useState(false)
  const [drumsError, setDrumsError] = useState<string | null>(null)
  const [drumsData, setDrumsData] = useState<DrumResult | null>(null)

  // Insert state
  const [chordsInsertStatus, setChordsInsertStatus] = useState<InsertStatus>('pending')
  const [chordsInsertError, setChordsInsertError] = useState<string | null>(null)
  const [drumsInsertStatus, setDrumsInsertStatus] = useState<InsertStatus>('pending')
  const [drumsInsertError, setDrumsInsertError] = useState<string | null>(null)

  // ── Auto-trigger: step 1 — chords ─────────────────────────────────────────
  const fetchChords = async () => {
    setChordsLoading(true)
    setChordsError(null)
    setChordsData(null)
    try {
      const res = await mcpClient.callTool({
        name: 'suggest_chord_progression',
        params: { key: keyVal, mood, genre, bars },
      })
      if (!res.success) {
        setChordsError(res.error ?? 'Tool call failed')
      } else {
        setChordsData(res.data as ChordResult)
      }
    } catch (e) {
      setChordsError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setChordsLoading(false)
    }
  }

  useEffect(() => {
    if (step === 1) { void fetchChords() }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Auto-trigger: step 2 — bass ───────────────────────────────────────────
  const fetchBass = async () => {
    setBassLoading(true)
    setBassError(null)
    setBassData(null)
    try {
      const root = keyVal.split(' ')[0] ?? 'A'
      const res = await mcpClient.callTool({
        name: 'generate_bassline',
        params: { root, genre, bpm: 128, bars },
      })
      if (!res.success) {
        setBassError(res.error ?? 'Tool call failed')
      } else {
        setBassData(res.data as BassResult)
      }
    } catch (e) {
      setBassError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setBassLoading(false)
    }
  }

  useEffect(() => {
    if (step === 2) { void fetchBass() }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Auto-trigger: step 3 — drums ──────────────────────────────────────────
  const fetchDrums = async () => {
    setDrumsLoading(true)
    setDrumsError(null)
    setDrumsData(null)
    try {
      const res = await mcpClient.callTool({
        name: 'generate_drum_pattern',
        params: { genre, bpm: 128, bars },
      })
      if (!res.success) {
        setDrumsError(res.error ?? 'Tool call failed')
      } else {
        setDrumsData(res.data as DrumResult)
      }
    } catch (e) {
      setDrumsError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setDrumsLoading(false)
    }
  }

  useEffect(() => {
    if (step === 3) { void fetchDrums() }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Insert handlers ───────────────────────────────────────────────────────
  const handleInsertChords = async () => {
    if (!chordsData) return
    setChordsInsertStatus('loading')
    setChordsInsertError(null)
    try {
      const res = await mcpClient.callTool({
        name: 'ableton_insert_notes',
        params: { notes: chordsData.chords.join(' '), bpm: 128 },
      })
      setChordsInsertStatus(res.success ? 'success' : 'error')
      if (!res.success) setChordsInsertError(res.error ?? 'Insert failed')
    } catch (e) {
      setChordsInsertStatus('error')
      setChordsInsertError(e instanceof Error ? e.message : 'Unknown error')
    }
  }

  const handleInsertDrums = async () => {
    if (!drumsData) return
    setDrumsInsertStatus('loading')
    setDrumsInsertError(null)
    try {
      const res = await mcpClient.callTool({
        name: 'ableton_insert_drums',
        params: { hits: drumsData.patterns, bpm: 128, bars },
      })
      setDrumsInsertStatus(res.success ? 'success' : 'error')
      if (!res.success) setDrumsInsertError(res.error ?? 'Insert failed')
    } catch (e) {
      setDrumsInsertStatus('error')
      setDrumsInsertError(e instanceof Error ? e.message : 'Unknown error')
    }
  }

  // ── Step definitions ──────────────────────────────────────────────────────
  const STEP_LABELS = ['Setup', 'Chords', 'Bass', 'Drums', 'Insert']
  const steps: WorkflowStep[] = STEP_LABELS.map((label, i) => ({
    label,
    status: i < step ? 'done' : i === step ? 'active' : 'pending',
  }))

  // ── Navigation ────────────────────────────────────────────────────────────
  const isLoading =
    (step === 1 && chordsLoading) ||
    (step === 2 && bassLoading) ||
    (step === 3 && drumsLoading)

  const nextDisabled =
    (step === 1 && (chordsLoading || !!chordsError || !chordsData)) ||
    (step === 2 && (bassLoading || !!bassError || !bassData)) ||
    (step === 3 && (drumsLoading || !!drumsError || !drumsData))

  const handleBack = step > 0 ? () => setStep(s => s - 1) : undefined
  const handleNext = step < 4 ? () => setStep(s => s + 1) : undefined

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <WorkflowShell
      title="Compose"
      icon="♪"
      steps={steps}
      currentStep={step}
      onBack={handleBack}
      onNext={step < 4 ? handleNext : undefined}
      nextLabel={step === 3 ? 'Insert →' : 'Next →'}
      nextDisabled={nextDisabled}
      isLoading={isLoading}
      onClose={() => setWorkflow(null)}
    >
      {step === 0 && (
        <SetupStep
          keyVal={keyVal}
          mood={mood}
          genre={genre}
          bars={bars}
          onKeyChange={setKeyVal}
          onMoodChange={setMood}
          onGenreChange={setGenre}
          onBarsChange={setBars}
        />
      )}

      {step === 1 && (
        <ChordsStep
          loading={chordsLoading}
          error={chordsError}
          result={chordsData}
          onRetry={fetchChords}
        />
      )}

      {step === 2 && (
        <BassStep
          loading={bassLoading}
          error={bassError}
          result={bassData}
          onRetry={fetchBass}
        />
      )}

      {step === 3 && (
        <DrumsStep
          loading={drumsLoading}
          error={drumsError}
          result={drumsData}
          onRetry={fetchDrums}
        />
      )}

      {step === 4 && (
        <InsertStep
          bars={bars}
          chordsData={chordsData}
          drumsData={drumsData}
          chordsStatus={chordsInsertStatus}
          drumsStatus={drumsInsertStatus}
          chordsError={chordsInsertError}
          drumsError={drumsInsertError}
          onInsertChords={() => { void handleInsertChords() }}
          onInsertDrums={() => { void handleInsertDrums() }}
          onDone={() => setWorkflow(null)}
        />
      )}
    </WorkflowShell>
  )
}
