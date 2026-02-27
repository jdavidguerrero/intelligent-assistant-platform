/**
 * VersionHistory — Mix version snapshot tracker.
 *
 * Saves mix analysis snapshots to localStorage, supports:
 *   - Manual save with label + metadata
 *   - Multi-select (click + Ctrl/Cmd) for side-by-side comparison
 *   - Client-side diff: health, spectral bands, problems resolved/added
 *   - Health score timeline chart (SVG, shown when 3+ versions)
 */

import React, { useState, useCallback, useEffect } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface MixVersionEntry {
  version_id: string
  timestamp: string
  label: string
  health_score: number
  problems_count: number
  genre: string
  file_path: string
  spectral_bands: Record<string, number>
  dynamics: {
    lufs: number
    rms_db: number
    crest_factor_db: number
  }
  stereo_width: number | null
  problems: { category: string; severity: number }[]
}

interface SaveModalState {
  open: boolean
  label: string
  filePath: string
  genre: string
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'mix_version_history'
const MAX_ENTRIES = 20

const SPECTRAL_BANDS = [
  'sub', 'low', 'low_mid', 'mid', 'high_mid', 'high', 'air',
] as const

type SpectralBand = (typeof SPECTRAL_BANDS)[number]

// Bands where lower (more negative) is better — sub-bass, low, low_mid tend to
// be over-represented; a drop means improvement.
const LOWER_IS_BETTER = new Set<string>(['sub', 'low', 'low_mid'])

// ── Local storage helpers ─────────────────────────────────────────────────────

function loadVersions(): MixVersionEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw) as MixVersionEntry[]
  } catch {
    return []
  }
}

function saveVersions(versions: MixVersionEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(versions))
  } catch {
    // Storage full — silently ignore
  }
}

function generateId(): string {
  return `v-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

// ── Time formatting ───────────────────────────────────────────────────────────

function relativeTime(isoString: string): string {
  const now = Date.now()
  const then = new Date(isoString).getTime()
  const diffSec = Math.floor((now - then) / 1000)

  if (diffSec < 60) return 'just now'
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
  return `${Math.floor(diffSec / 86400)}d ago`
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[9px] uppercase tracking-[0.08em] text-push-muted block mb-1">
      {children}
    </span>
  )
}

function HealthBadge({ score }: { score: number }) {
  const color =
    score >= 75 ? '#7EB13D' :
    score >= 50 ? '#E5C020' :
                  '#E53935'
  return (
    <span
      className="text-[10px] font-mono font-bold rounded-[3px] px-1.5 py-0.5 border"
      style={{ color, borderColor: color }}
    >
      {score}
    </span>
  )
}

// ── Save Modal ────────────────────────────────────────────────────────────────

interface SaveModalProps {
  state: SaveModalState
  onChange: (patch: Partial<SaveModalState>) => void
  onSave: () => void
  onCancel: () => void
}

const SUPPORTED_GENRES = [
  'organic house',
  'melodic techno',
  'deep house',
  'progressive house',
  'afro house',
]

function SaveModal({ state, onChange, onSave, onCancel }: SaveModalProps) {
  const inputClass =
    'w-full bg-push-elevated border border-push-border rounded-[3px] ' +
    'text-[11px] text-push-text px-2 py-1.5 ' +
    'placeholder:text-push-muted ' +
    'focus:outline-none focus:border-push-orange transition-colors'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onClick={e => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div
        className="bg-push-surface border border-push-border rounded-[4px] w-80 p-4 flex flex-col gap-3 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label="Save mix version"
      >
        <span className="text-[11px] uppercase tracking-[0.08em] text-push-text font-medium">
          Save Version
        </span>

        <div className="flex flex-col gap-0.5">
          <SectionLabel>Label</SectionLabel>
          <input
            type="text"
            className={inputClass}
            value={state.label}
            onChange={e => onChange({ label: e.target.value })}
            placeholder="e.g. After low-cut on kick"
            autoFocus
            onKeyDown={e => {
              if (e.key === 'Enter' && state.label.trim()) onSave()
              if (e.key === 'Escape') onCancel()
            }}
          />
        </div>

        <div className="flex flex-col gap-0.5">
          <SectionLabel>File Path</SectionLabel>
          <input
            type="text"
            className={inputClass}
            value={state.filePath}
            onChange={e => onChange({ filePath: e.target.value })}
            placeholder="/path/to/mix.wav"
            spellCheck={false}
          />
        </div>

        <div className="flex flex-col gap-0.5">
          <SectionLabel>Genre</SectionLabel>
          <select
            className={inputClass}
            value={state.genre}
            onChange={e => onChange({ genre: e.target.value })}
          >
            {SUPPORTED_GENRES.map(g => (
              <option key={g} value={g}>{g}</option>
            ))}
          </select>
        </div>

        <div className="flex gap-2 justify-end pt-1">
          <button
            onClick={onCancel}
            className="px-3 py-1 text-[10px] uppercase tracking-[0.06em]
                       text-push-muted hover:text-push-text transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onSave}
            disabled={!state.label.trim()}
            className="px-3 py-1 rounded-[3px] border border-push-orange text-push-orange
                       text-[10px] uppercase tracking-[0.06em]
                       hover:bg-push-orange hover:text-push-bg
                       disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Per-band comparison bars ──────────────────────────────────────────────────

interface BandCompareRowProps {
  band: string
  v1Value: number
  v2Value: number
}

function BandCompareRow({ band, v1Value, v2Value }: BandCompareRowProps) {
  const delta = v2Value - v1Value
  const improved = LOWER_IS_BETTER.has(band) ? delta < 0 : delta > 0
  const deltaColor = Math.abs(delta) < 0.1 ? '#888888' : improved ? '#7EB13D' : '#E53935'

  // Normalize bar widths relative to each other. Show them on a shared scale.
  // Both values are negative dBFS; closer to 0 = louder/more energy.
  // We map onto a 0–100 display scale anchored at -40dBFS to 0dBFS.
  const normalize = (v: number) => Math.max(0, Math.min(100, ((v + 40) / 40) * 100))

  const w1 = normalize(v1Value)
  const w2 = normalize(v2Value)

  return (
    <div className="flex items-center gap-2">
      {/* Band label */}
      <span className="text-[9px] font-mono text-push-muted w-12 flex-shrink-0 uppercase">
        {band}
      </span>

      {/* Bars */}
      <div className="flex-1 flex flex-col gap-0.5">
        {/* V1 bar */}
        <div className="flex items-center gap-1">
          <div className="flex-1 h-1.5 bg-push-elevated rounded-full overflow-hidden">
            <div
              className="h-full rounded-full"
              style={{ width: `${w1}%`, backgroundColor: '#888888' }}
            />
          </div>
          <span className="text-[8px] font-mono text-push-muted w-10 text-right">
            {v1Value.toFixed(1)}
          </span>
        </div>
        {/* V2 bar */}
        <div className="flex items-center gap-1">
          <div className="flex-1 h-1.5 bg-push-elevated rounded-full overflow-hidden">
            <div
              className="h-full rounded-full"
              style={{ width: `${w2}%`, backgroundColor: '#FF7700' }}
            />
          </div>
          <span className="text-[8px] font-mono w-10 text-right" style={{ color: '#FF7700' }}>
            {v2Value.toFixed(1)}
          </span>
        </div>
      </div>

      {/* Delta */}
      <span
        className="text-[9px] font-mono w-12 text-right flex-shrink-0"
        style={{ color: deltaColor }}
      >
        {delta > 0 ? '+' : ''}{delta.toFixed(1)}
      </span>
    </div>
  )
}

// ── Health Score Timeline Chart ───────────────────────────────────────────────

function HealthTimeline({ versions }: { versions: MixVersionEntry[] }) {
  if (versions.length < 3) return null

  const W = 600
  const H = 80
  const PAD_L = 32
  const PAD_R = 8
  const PAD_T = 10
  const PAD_B = 20
  const innerW = W - PAD_L - PAD_R
  const innerH = H - PAD_T - PAD_B

  // Versions in chronological order (oldest first)
  const ordered = [...versions].reverse()

  const toX = (i: number) => PAD_L + (i / (ordered.length - 1)) * innerW
  const toY = (s: number) => PAD_T + (1 - s / 100) * innerH

  function makePath(pts: { x: number; y: number }[]): string {
    if (pts.length < 2) return ''
    let d = `M ${pts[0].x} ${pts[0].y}`
    for (let i = 1; i < pts.length; i++) {
      const prev = pts[i - 1]
      const curr = pts[i]
      const cpX = (prev.x + curr.x) / 2
      d += ` C ${cpX} ${prev.y}, ${cpX} ${curr.y}, ${curr.x} ${curr.y}`
    }
    return d
  }

  const svgPoints = ordered.map((v, i) => ({
    x: toX(i),
    y: toY(v.health_score),
    label: v.label,
    score: v.health_score,
  }))

  const pathD = makePath(svgPoints)

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={H}
      style={{ display: 'block' }}
      aria-label="Health score timeline"
    >
      {/* Grid lines at 25, 50, 75 */}
      {[25, 50, 75].map(tick => {
        const y = toY(tick)
        return (
          <g key={tick}>
            <line
              x1={PAD_L} y1={y} x2={W - PAD_R} y2={y}
              stroke="#2E2E2E" strokeWidth="0.5" strokeDasharray="3 3"
            />
            <text
              x={PAD_L - 3} y={y}
              textAnchor="end" dominantBaseline="central"
              fontSize="7" fill="#888888" fontFamily="monospace"
            >
              {tick}
            </text>
          </g>
        )
      })}

      {/* Line */}
      <path d={pathD} fill="none" stroke="#FF7700" strokeWidth="1.5" strokeLinecap="round" />

      {/* Points + labels */}
      {svgPoints.map((pt, i) => {
        const color =
          pt.score >= 75 ? '#7EB13D' :
          pt.score >= 50 ? '#E5C020' :
                           '#E53935'
        return (
          <g key={i}>
            <circle cx={pt.x} cy={pt.y} r="3" fill={color} />
            {/* Label — alternate above/below to avoid overlap */}
            <text
              x={pt.x}
              y={i % 2 === 0 ? pt.y - 6 : pt.y + 12}
              textAnchor="middle"
              fontSize="7"
              fill="#888888"
              fontFamily="monospace"
            >
              {pt.label.length > 8 ? pt.label.slice(0, 8) + '…' : pt.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

// ── Comparison panel ──────────────────────────────────────────────────────────

interface ComparisonPanelProps {
  v1: MixVersionEntry
  v2: MixVersionEntry
}

function ComparisonPanel({ v1, v2 }: ComparisonPanelProps) {
  const healthDelta = v2.health_score - v1.health_score
  const healthColor = healthDelta > 0 ? '#7EB13D' : healthDelta < 0 ? '#E53935' : '#888888'

  // Problem sets (by category string)
  const v1Categories = new Set(v1.problems.map(p => p.category))
  const v2Categories = new Set(v2.problems.map(p => p.category))

  const resolved = v1.problems
    .filter(p => !v2Categories.has(p.category))
    .map(p => p.category)

  const newProblems = v2.problems
    .filter(p => !v1Categories.has(p.category))
    .map(p => p.category)

  // Summary sentence
  const healthPart =
    healthDelta === 0 ? 'Health unchanged' :
    healthDelta > 0 ? `Health improved by +${healthDelta} pts` :
                      `Health decreased by ${healthDelta} pts`
  const resolvedPart = resolved.length > 0 ? `Resolved: ${resolved.join(', ')}.` : ''
  const newPart = newProblems.length > 0 ? `New: ${newProblems.join(', ')}.` : ''
  const summarySentence = [healthPart, resolvedPart, newPart].filter(Boolean).join('. ') + '.'

  // Stereo delta
  const stereoDelta =
    v1.stereo_width !== null && v2.stereo_width !== null
      ? v2.stereo_width - v1.stereo_width
      : null

  return (
    <div className="flex flex-col gap-3 h-full overflow-y-auto">

      {/* Version labels */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-1.5 bg-push-elevated border border-push-border rounded-[3px] px-2 py-1">
          <span className="w-2 h-2 rounded-full bg-push-muted flex-shrink-0" />
          <span className="text-[9px] text-push-muted">{v1.label}</span>
        </div>
        <span className="text-[9px] text-push-muted">vs</span>
        <div className="flex items-center gap-1.5 bg-push-elevated border border-push-orange rounded-[3px] px-2 py-1">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: '#FF7700' }} />
          <span className="text-[9px] text-push-orange">{v2.label}</span>
        </div>
      </div>

      {/* Summary sentence */}
      <div className="bg-push-surface border border-push-border rounded-[3px] px-3 py-2">
        <p className="text-[10px] text-push-text leading-relaxed">{summarySentence}</p>
      </div>

      {/* Health delta */}
      <div className="flex items-center gap-3">
        <div className="flex flex-col items-center bg-push-elevated border border-push-border rounded-[3px] px-3 py-1.5">
          <span className="text-[8px] uppercase tracking-[0.06em] text-push-muted">V1 Health</span>
          <span className="text-[13px] font-mono text-push-muted">{v1.health_score}</span>
        </div>
        <span
          className="text-[13px] font-mono font-bold"
          style={{ color: healthColor }}
        >
          {healthDelta > 0 ? `+${healthDelta}` : String(healthDelta)}
        </span>
        <div className="flex flex-col items-center bg-push-elevated border border-push-border rounded-[3px] px-3 py-1.5">
          <span className="text-[8px] uppercase tracking-[0.06em] text-push-muted">V2 Health</span>
          <span className="text-[13px] font-mono" style={{ color: healthColor }}>
            {v2.health_score}
          </span>
        </div>

        {stereoDelta !== null && (
          <div className="ml-auto flex flex-col items-center bg-push-elevated border border-push-border rounded-[3px] px-3 py-1.5">
            <span className="text-[8px] uppercase tracking-[0.06em] text-push-muted">Stereo Δ</span>
            <span
              className="text-[12px] font-mono"
              style={{ color: Math.abs(stereoDelta) < 0.01 ? '#888888' : stereoDelta > 0 ? '#7EB13D' : '#E53935' }}
            >
              {stereoDelta > 0 ? '+' : ''}{stereoDelta.toFixed(2)}
            </span>
          </div>
        )}
      </div>

      {/* Spectral band comparison */}
      <div>
        <SectionLabel>Spectral Bands (dBFS)</SectionLabel>
        <div className="flex flex-col gap-1.5">
          {SPECTRAL_BANDS.map(band => {
            const bk = band as SpectralBand
            const val1 = v1.spectral_bands[bk] ?? 0
            const val2 = v2.spectral_bands[bk] ?? 0
            return (
              <BandCompareRow
                key={band}
                band={band}
                v1Value={val1}
                v2Value={val2}
              />
            )
          })}
        </div>
        <div className="flex gap-4 mt-1.5">
          <div className="flex items-center gap-1">
            <span className="w-3 h-1 rounded-full bg-push-muted" />
            <span className="text-[8px] text-push-muted">{v1.label}</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-3 h-1 rounded-full" style={{ backgroundColor: '#FF7700' }} />
            <span className="text-[8px] text-push-muted">{v2.label}</span>
          </div>
        </div>
      </div>

      {/* Resolved / New problems */}
      {(resolved.length > 0 || newProblems.length > 0) && (
        <div className="flex gap-2">
          {resolved.length > 0 && (
            <div className="flex-1 bg-push-surface border border-push-border rounded-[3px] p-2">
              <SectionLabel>Resolved</SectionLabel>
              <div className="flex flex-col gap-0.5">
                {resolved.map(cat => (
                  <span key={cat} className="text-[9px] text-push-green leading-snug">
                    ✓ {cat}
                  </span>
                ))}
              </div>
            </div>
          )}
          {newProblems.length > 0 && (
            <div className="flex-1 bg-push-surface border border-push-border rounded-[3px] p-2">
              <SectionLabel>New Problems</SectionLabel>
              <div className="flex flex-col gap-0.5">
                {newProblems.map(cat => (
                  <span key={cat} className="text-[9px] text-push-red leading-snug">
                    ✗ {cat}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Dynamics comparison */}
      <div>
        <SectionLabel>Dynamics</SectionLabel>
        <div className="flex gap-2">
          {(
            [
              ['LUFS', v1.dynamics.lufs, v2.dynamics.lufs, true],
              ['RMS dB', v1.dynamics.rms_db, v2.dynamics.rms_db, true],
              ['Crest Factor', v1.dynamics.crest_factor_db, v2.dynamics.crest_factor_db, false],
            ] as [string, number, number, boolean][]
          ).map(([label, val1, val2, lowerIsBetter]) => {
            const delta = val2 - val1
            const improved = lowerIsBetter ? delta < 0 : delta > 0
            const dc = Math.abs(delta) < 0.05 ? '#888888' : improved ? '#7EB13D' : '#E53935'
            return (
              <div
                key={label}
                className="flex-1 bg-push-elevated border border-push-border rounded-[3px] px-2 py-1.5 flex flex-col gap-0.5"
              >
                <span className="text-[8px] uppercase tracking-[0.06em] text-push-muted">{label}</span>
                <div className="flex items-center gap-1">
                  <span className="text-[10px] font-mono text-push-muted">{val1.toFixed(1)}</span>
                  <span className="text-[8px] text-push-muted">→</span>
                  <span className="text-[10px] font-mono" style={{ color: dc }}>
                    {val2.toFixed(1)}
                  </span>
                </div>
                <span className="text-[8px] font-mono" style={{ color: dc }}>
                  {delta > 0 ? '+' : ''}{delta.toFixed(1)}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function VersionHistory() {
  const [versions, setVersions] = useState<MixVersionEntry[]>(loadVersions)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [modal, setModal] = useState<SaveModalState>({
    open: false,
    label: '',
    filePath: '',
    genre: 'organic house',
  })

  // Persist on change
  useEffect(() => {
    saveVersions(versions)
  }, [versions])

  // Compute selected version objects (in selection order)
  const selected = selectedIds
    .map(id => versions.find(v => v.version_id === id))
    .filter((v): v is MixVersionEntry => v !== undefined)

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleSelect = useCallback(
    (id: string, e: React.MouseEvent) => {
      const multiKey = e.ctrlKey || e.metaKey
      setSelectedIds(prev => {
        if (multiKey) {
          // Toggle: add or remove from selection (max 2)
          if (prev.includes(id)) {
            return prev.filter(x => x !== id)
          }
          if (prev.length >= 2) {
            // Replace oldest selection
            return [prev[1], id]
          }
          return [...prev, id]
        }
        // Single click: replace selection
        return prev.length === 1 && prev[0] === id ? [] : [id]
      })
    },
    []
  )

  const handleSave = useCallback(() => {
    if (!modal.label.trim()) return

    const newEntry: MixVersionEntry = {
      version_id: generateId(),
      timestamp: new Date().toISOString(),
      label: modal.label.trim(),
      health_score: 0,           // Placeholder — caller should inject real data
      problems_count: 0,
      genre: modal.genre,
      file_path: modal.filePath.trim(),
      spectral_bands: {},
      dynamics: { lufs: 0, rms_db: 0, crest_factor_db: 0 },
      stereo_width: null,
      problems: [],
    }

    setVersions(prev => {
      const updated = [newEntry, ...prev].slice(0, MAX_ENTRIES)
      return updated
    })
    setModal(prev => ({ ...prev, open: false, label: '' }))
  }, [modal])

  const handleClearHistory = useCallback(() => {
    if (!window.confirm('Clear all version history? This cannot be undone.')) return
    setVersions([])
    setSelectedIds([])
  }, [])

  // ── Render ──────────────────────────────────────────────────────────────────

  // Versions newest-first (already stored newest-first, but make it explicit)
  const displayVersions = versions.slice(0, MAX_ENTRIES)

  return (
    <div className="flex flex-col h-full bg-push-bg text-push-text">

      {/* ── Top bar ────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-push-border flex-shrink-0">
        <span className="text-[9px] uppercase tracking-[0.08em] text-push-muted flex-1">
          Version History
        </span>
        <button
          onClick={() => setModal(prev => ({ ...prev, open: true }))}
          className="px-3 py-1 rounded-[3px] border border-push-orange text-push-orange
                     text-[10px] uppercase tracking-[0.06em]
                     hover:bg-push-orange hover:text-push-bg transition-colors"
        >
          Save Current Version
        </button>
        <button
          onClick={handleClearHistory}
          className="px-2 py-1 rounded-[3px] border border-push-border text-push-muted
                     text-[10px] uppercase tracking-[0.06em]
                     hover:border-push-red hover:text-push-red transition-colors"
        >
          Clear
        </button>
      </div>

      {/* ── Main body (two columns) ────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden min-h-0">

        {/* Left column — version list */}
        <div
          className="flex-shrink-0 border-r border-push-border overflow-y-auto"
          style={{ width: '35%' }}
        >
          {displayVersions.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 gap-2">
              <span className="text-[10px] text-push-muted">No versions saved yet.</span>
              <span className="text-[9px] text-push-muted opacity-60">
                Click "Save Current Version" to start tracking.
              </span>
            </div>
          ) : (
            <div className="flex flex-col gap-0 divide-y divide-push-border">
              {displayVersions.map(v => {
                const isSelected = selectedIds.includes(v.version_id)
                const selectionIndex = selectedIds.indexOf(v.version_id)
                return (
                  <button
                    key={v.version_id}
                    onClick={e => handleSelect(v.version_id, e)}
                    className="w-full text-left px-2 py-2 flex items-start gap-2
                               hover:bg-push-surface transition-colors focus:outline-none"
                    style={{
                      borderLeft: isSelected
                        ? '2px solid #FF7700'
                        : '2px solid transparent',
                      background: isSelected ? 'rgba(255,119,0,0.05)' : undefined,
                    }}
                  >
                    {/* Selection index indicator */}
                    {isSelected && (
                      <span
                        className="text-[8px] font-mono font-bold rounded-full w-3.5 h-3.5
                                   flex items-center justify-center flex-shrink-0 mt-0.5"
                        style={{ background: '#FF7700', color: '#0F0F0F' }}
                      >
                        {selectionIndex + 1}
                      </span>
                    )}

                    {/* Content */}
                    <div className="flex-1 min-w-0 flex flex-col gap-0.5">
                      <div className="flex items-center gap-1.5 justify-between">
                        <span className="text-[10px] text-push-text font-medium truncate">
                          {v.label}
                        </span>
                        <HealthBadge score={v.health_score} />
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[8px] text-push-muted">
                          {relativeTime(v.timestamp)}
                        </span>
                        {v.problems_count > 0 && (
                          <span className="text-[8px] text-push-red">
                            {v.problems_count} {v.problems_count === 1 ? 'problem' : 'problems'}
                          </span>
                        )}
                      </div>
                      {v.genre && (
                        <span className="text-[8px] text-push-muted opacity-70 truncate">
                          {v.genre}
                        </span>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          )}

          {/* Selection hint */}
          {displayVersions.length > 1 && selectedIds.length < 2 && (
            <div className="px-2 py-2 border-t border-push-border">
              <span className="text-[8px] text-push-muted italic">
                Ctrl+click to select two versions for comparison
              </span>
            </div>
          )}
        </div>

        {/* Right column — comparison or empty state */}
        <div className="flex-1 overflow-y-auto p-3">
          {selected.length === 2 ? (
            <ComparisonPanel v1={selected[0]} v2={selected[1]} />
          ) : selected.length === 1 ? (
            <div className="flex flex-col gap-3">
              <div>
                <SectionLabel>Selected</SectionLabel>
                <div className="bg-push-surface border border-push-border rounded-[3px] p-3 flex flex-col gap-1">
                  <span className="text-[11px] text-push-text font-medium">{selected[0].label}</span>
                  <span className="text-[9px] text-push-muted">
                    {new Date(selected[0].timestamp).toLocaleString()}
                  </span>
                  <span className="text-[9px] text-push-muted">{selected[0].genre}</span>
                  {selected[0].file_path && (
                    <span className="text-[9px] text-push-muted font-mono break-all">
                      {selected[0].file_path}
                    </span>
                  )}
                  <div className="flex items-center gap-2 mt-1">
                    <HealthBadge score={selected[0].health_score} />
                    <span className="text-[9px] text-push-muted">
                      {selected[0].problems_count} problems
                    </span>
                  </div>
                </div>
              </div>
              <span className="text-[9px] text-push-muted italic">
                Ctrl+click another version to compare
              </span>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-2 opacity-50">
              <span className="text-[10px] text-push-muted">
                Select a version to inspect or two to compare
              </span>
            </div>
          )}

          {/* Health score timeline — shown at the bottom when 3+ versions */}
          {versions.length >= 3 && (
            <div className="mt-4 border-t border-push-border pt-3">
              <SectionLabel>Health Score Over Time</SectionLabel>
              <div className="border border-push-border rounded-[3px] overflow-hidden bg-push-surface">
                <HealthTimeline versions={versions} />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Save Modal ─────────────────────────────────────────────────── */}
      {modal.open && (
        <SaveModal
          state={modal}
          onChange={patch => setModal(prev => ({ ...prev, ...patch }))}
          onSave={handleSave}
          onCancel={() => setModal(prev => ({ ...prev, open: false }))}
        />
      )}
    </div>
  )
}
