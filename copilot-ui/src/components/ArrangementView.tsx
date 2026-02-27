/**
 * ArrangementView — Arrangement analysis panel.
 *
 * Calls the `analyze_arrangement` MCP tool and renders:
 *   - Section timeline (proportional colored blocks with hover tooltips)
 *   - Energy curve (SVG bezier line chart with drop highlights)
 *   - Arrangement score badge
 *   - Problems list (collapsible rows, severity-sorted)
 *   - Energy flow stat cards
 */

import React, { useState, useRef, useCallback } from 'react'
import { mcpClient } from '../services/mcpClient'

// ── Types ─────────────────────────────────────────────────────────────────────

type SectionType =
  | 'intro'
  | 'buildup'
  | 'drop'
  | 'breakdown'
  | 'outro'
  | 'transition'
  | 'unknown'

interface ArrangementSection {
  section_type: SectionType
  start_sec: number
  end_sec: number
  energy_db: number
  bars: number
}

interface ArrangementProblem {
  problem_type: string
  description: string
  suggestion: string
  severity: number
}

interface EnergyFlow {
  drop_count: number
  breakdown_count: number
  buildup_count: number
  drop_breakdown_ratio: number
  buildup_ascending: boolean
}

interface ArrangementResult {
  sections: ArrangementSection[]
  problems: ArrangementProblem[]
  arrangement_score: number
  energy_flow: EnergyFlow
  total_duration_sec: number
}

interface ArrangementViewProps {
  filePath?: string
  genre?: string
  bpm?: number
}

// ── Constants ─────────────────────────────────────────────────────────────────

const SECTION_COLORS: Record<SectionType, string> = {
  intro:      '#888888',
  buildup:    '#E5C020',
  drop:       '#FF7700',
  breakdown:  '#9B59B6',
  outro:      '#888888',
  transition: '#00BCD4',
  unknown:    '#444444',
}

const SECTION_ABBR: Record<SectionType, string> = {
  intro:      'INT',
  buildup:    'BLD',
  drop:       'DRP',
  breakdown:  'BRK',
  outro:      'OTR',
  transition: 'TRN',
  unknown:    '???',
}

const SUPPORTED_GENRES = [
  'organic house',
  'melodic techno',
  'deep house',
  'progressive house',
  'afro house',
]

// ── Sub-components ────────────────────────────────────────────────────────────

function LoadingSpinner() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12">
      <div className="w-6 h-6 rounded-full border-2 border-push-border border-t-push-orange animate-spin" />
      <span className="text-[10px] text-push-muted uppercase tracking-[0.08em]">
        Analyzing arrangement…
      </span>
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[9px] uppercase tracking-[0.08em] text-push-muted block mb-2">
      {children}
    </span>
  )
}

// ── Score badge ───────────────────────────────────────────────────────────────

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 75 ? '#7EB13D' :
    score >= 50 ? '#E5C020' :
                  '#E53935'

  const r = 18
  const circ = 2 * Math.PI * r
  const dash = circ * (score / 100)

  return (
    <div className="flex flex-col items-center gap-0.5" title={`Arrangement score: ${score}/100`}>
      <svg width="48" height="48" viewBox="0 0 48 48">
        <circle cx="24" cy="24" r={r} fill="none" stroke="#2E2E2E" strokeWidth="4" />
        <circle
          cx="24" cy="24" r={r}
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeDasharray={`${dash} ${circ - dash}`}
          strokeLinecap="round"
          transform="rotate(-90 24 24)"
        />
        <text
          x="24" y="24"
          textAnchor="middle"
          dominantBaseline="central"
          fontSize="10"
          fontWeight="bold"
          fill={color}
          fontFamily="monospace"
        >
          {score}
        </text>
      </svg>
      <span className="text-[8px] uppercase tracking-[0.06em] text-push-muted">Score</span>
    </div>
  )
}

// ── Section Timeline ──────────────────────────────────────────────────────────

interface TooltipState {
  visible: boolean
  x: number
  y: number
  content: string[]
}

function SectionTimeline({ sections, totalDuration }: {
  sections: ArrangementSection[]
  totalDuration: number
}) {
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false, x: 0, y: 0, content: [],
  })
  const containerRef = useRef<HTMLDivElement>(null)

  const handleMouseEnter = useCallback(
    (e: React.MouseEvent<HTMLDivElement>, section: ArrangementSection) => {
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top
      setTooltip({
        visible: true,
        x,
        y,
        content: [
          section.section_type.toUpperCase(),
          `${section.start_sec.toFixed(1)}s – ${section.end_sec.toFixed(1)}s`,
          `Energy: ${section.energy_db.toFixed(1)} dBFS`,
          `${section.bars} bars`,
        ],
      })
    },
    []
  )

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top
      setTooltip(prev => ({ ...prev, x, y }))
    },
    []
  )

  const handleMouseLeave = useCallback(() => {
    setTooltip(prev => ({ ...prev, visible: false }))
  }, [])

  return (
    <div ref={containerRef} className="relative select-none">
      {/* Blocks row */}
      <div className="flex h-8 rounded-[3px] overflow-hidden border border-push-border">
        {sections.map((s, i) => {
          const widthPct = ((s.end_sec - s.start_sec) / totalDuration) * 100
          return (
            <div
              key={i}
              style={{
                width: `${widthPct}%`,
                backgroundColor: SECTION_COLORS[s.section_type],
                minWidth: '1px',
              }}
              className="relative cursor-default transition-opacity duration-100 hover:opacity-80"
              onMouseEnter={e => handleMouseEnter(e, s)}
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
            />
          )
        })}
      </div>

      {/* Labels row */}
      <div className="flex mt-1">
        {sections.map((s, i) => {
          const widthPct = ((s.end_sec - s.start_sec) / totalDuration) * 100
          return (
            <div
              key={i}
              style={{ width: `${widthPct}%`, minWidth: '1px' }}
              className="overflow-hidden"
            >
              {widthPct > 4 && (
                <span
                  className="text-[8px] font-mono uppercase block text-center leading-none"
                  style={{ color: SECTION_COLORS[s.section_type] }}
                >
                  {SECTION_ABBR[s.section_type]}
                </span>
              )}
            </div>
          )
        })}
      </div>

      {/* Tooltip */}
      {tooltip.visible && (
        <div
          className="absolute z-50 pointer-events-none"
          style={{ left: tooltip.x + 8, top: tooltip.y - 8 }}
        >
          <div className="bg-push-elevated border border-push-border rounded-[3px] px-2 py-1.5 shadow-lg">
            {tooltip.content.map((line, i) => (
              <div
                key={i}
                className={`text-[9px] font-mono leading-snug ${
                  i === 0 ? 'text-push-orange font-bold' : 'text-push-muted'
                }`}
              >
                {line}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Energy Curve ──────────────────────────────────────────────────────────────

function EnergyCurve({ sections, totalDuration }: {
  sections: ArrangementSection[]
  totalDuration: number
}) {
  const W = 800
  const H = 100
  const PAD_L = 36
  const PAD_R = 8
  const PAD_T = 8
  const PAD_B = 16

  const innerW = W - PAD_L - PAD_R
  const innerH = H - PAD_T - PAD_B

  // Collect energy data points at section midpoints
  const points = sections.map(s => ({
    t: (s.start_sec + s.end_sec) / 2,
    energy: s.energy_db,
    isDropSection: s.section_type === 'drop',
  }))

  if (points.length === 0) return null

  const energyValues = points.map(p => p.energy)
  const minE = Math.min(...energyValues, -35)
  const maxE = Math.max(...energyValues, -3)

  const toX = (t: number) => PAD_L + (t / totalDuration) * innerW
  const toY = (e: number) => PAD_T + (1 - (e - minE) / (maxE - minE)) * innerH

  // Build smooth bezier path
  function makePath(pts: { x: number; y: number }[]): string {
    if (pts.length === 0) return ''
    if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y}`
    let d = `M ${pts[0].x} ${pts[0].y}`
    for (let i = 1; i < pts.length; i++) {
      const prev = pts[i - 1]
      const curr = pts[i]
      const cpX = (prev.x + curr.x) / 2
      d += ` C ${cpX} ${prev.y}, ${cpX} ${curr.y}, ${curr.x} ${curr.y}`
    }
    return d
  }

  const svgPoints = points.map(p => ({ x: toX(p.t), y: toY(p.energy) }))
  const pathD = makePath(svgPoints)

  // Y-axis tick values
  const yTicks = [-30, -20, -10, -6]

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={H}
      style={{ display: 'block' }}
      aria-label="Energy curve"
    >
      {/* Drop section vertical highlight bands */}
      {sections
        .filter(s => s.section_type === 'drop')
        .map((s, i) => (
          <rect
            key={i}
            x={toX(s.start_sec)}
            y={PAD_T}
            width={toX(s.end_sec) - toX(s.start_sec)}
            height={innerH}
            fill="#FF7700"
            fillOpacity="0.08"
          />
        ))
      }

      {/* Y-axis grid lines and labels */}
      {yTicks.map(tick => {
        if (tick < minE || tick > maxE) return null
        const y = toY(tick)
        return (
          <g key={tick}>
            <line
              x1={PAD_L} y1={y} x2={W - PAD_R} y2={y}
              stroke="#2E2E2E" strokeWidth="0.5" strokeDasharray="3 3"
            />
            <text
              x={PAD_L - 3} y={y}
              textAnchor="end"
              dominantBaseline="central"
              fontSize="7"
              fill="#888888"
              fontFamily="monospace"
            >
              {tick}
            </text>
          </g>
        )
      })}

      {/* X-axis baseline */}
      <line
        x1={PAD_L} y1={H - PAD_B} x2={W - PAD_R} y2={H - PAD_B}
        stroke="#2E2E2E" strokeWidth="1"
      />

      {/* Energy line */}
      <path
        d={pathD}
        fill="none"
        stroke="#FF7700"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Data points */}
      {svgPoints.map((pt, i) => (
        <circle
          key={i}
          cx={pt.x}
          cy={pt.y}
          r="2.5"
          fill="#FF7700"
          fillOpacity="0.9"
        />
      ))}

      {/* X-axis time labels (start/mid/end) */}
      {[0, 0.5, 1].map(frac => {
        const t = frac * totalDuration
        const x = toX(t)
        const label = t >= 60
          ? `${Math.floor(t / 60)}:${String(Math.round(t % 60)).padStart(2, '0')}`
          : `${Math.round(t)}s`
        return (
          <text
            key={frac}
            x={x}
            y={H - 2}
            textAnchor={frac === 0 ? 'start' : frac === 1 ? 'end' : 'middle'}
            fontSize="7"
            fill="#888888"
            fontFamily="monospace"
          >
            {label}
          </text>
        )
      })}
    </svg>
  )
}

// ── Problems List ─────────────────────────────────────────────────────────────

function ArrangementProblemsList({ problems }: { problems: ArrangementProblem[] }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const sorted = [...problems].sort((a, b) => b.severity - a.severity)

  if (sorted.length === 0) {
    return (
      <div className="p-2 text-[10px] text-push-muted italic">
        No arrangement problems detected.
      </div>
    )
  }

  const toggleRow = (i: number) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  const severityClass = (sev: number) =>
    sev >= 7 ? 'border-push-red text-push-red' :
    sev >= 4 ? 'border-push-yellow text-push-yellow' :
               'border-push-green text-push-green'

  return (
    <div className="flex flex-col gap-1">
      {sorted.map((p, i) => (
        <div
          key={i}
          className="border border-push-border rounded-[3px] overflow-hidden"
        >
          {/* Row header — always visible, click to toggle */}
          <button
            onClick={() => toggleRow(i)}
            className="w-full flex items-start gap-2 px-2 py-1.5 bg-push-surface
                       hover:bg-push-elevated transition-colors text-left"
          >
            {/* Severity badge */}
            <span
              className={`px-1.5 py-0.5 rounded-[3px] border text-[9px] font-mono flex-shrink-0 ${severityClass(p.severity)}`}
            >
              {p.severity}
            </span>

            {/* Problem type + description */}
            <div className="flex-1 min-w-0">
              <span className="text-[10px] text-push-orange font-medium uppercase tracking-[0.04em]">
                {p.problem_type}
              </span>
              <p className="text-[10px] text-push-muted leading-snug mt-0.5 line-clamp-2">
                {p.description}
              </p>
            </div>

            {/* Expand indicator */}
            <span className="text-[9px] text-push-muted flex-shrink-0 mt-0.5">
              {expanded.has(i) ? '▲' : '▼'}
            </span>
          </button>

          {/* Suggestion — expanded only */}
          {expanded.has(i) && (
            <div className="px-3 py-2 bg-push-elevated border-t border-push-border">
              <span className="text-[9px] uppercase tracking-[0.06em] text-push-muted block mb-1">
                Suggestion
              </span>
              <p className="text-[10px] text-push-text leading-relaxed">
                {p.suggestion}
              </p>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Energy Flow Stats ─────────────────────────────────────────────────────────

function EnergyFlowStats({ flow }: { flow: EnergyFlow }) {
  const ratio = flow.drop_breakdown_ratio
  // Target range: 0.5–2.0
  const inRange = ratio >= 0.5 && ratio <= 2.0
  const ratioColor = inRange ? '#7EB13D' : '#E5C020'

  return (
    <div className="grid grid-cols-3 gap-2">
      {/* Drop count */}
      <StatCard label="Drops" value={String(flow.drop_count)} />
      {/* Breakdown count */}
      <StatCard label="Breakdowns" value={String(flow.breakdown_count)} />
      {/* Buildup count */}
      <StatCard label="Buildups" value={String(flow.buildup_count)} />

      {/* Drop/Breakdown ratio */}
      <div className="col-span-2 flex flex-col bg-push-surface border border-push-border rounded-[3px] px-2 py-1.5">
        <span className="text-[8px] uppercase tracking-[0.06em] text-push-muted mb-0.5">
          Drop / Breakdown Ratio
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-mono" style={{ color: ratioColor }}>
            {ratio.toFixed(2)}
          </span>
          <span className="text-[9px] text-push-muted">
            {inRange ? '(target 0.5–2.0)' : '(outside target 0.5–2.0)'}
          </span>
        </div>
      </div>

      {/* Buildup ascending */}
      <div className="flex flex-col bg-push-surface border border-push-border rounded-[3px] px-2 py-1.5">
        <span className="text-[8px] uppercase tracking-[0.06em] text-push-muted mb-0.5">
          Buildup Ascending
        </span>
        <span
          className="text-[13px] font-bold"
          style={{ color: flow.buildup_ascending ? '#7EB13D' : '#E53935' }}
        >
          {flow.buildup_ascending ? '✓' : '✗'}
        </span>
      </div>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col bg-push-surface border border-push-border rounded-[3px] px-2 py-1.5">
      <span className="text-[8px] uppercase tracking-[0.06em] text-push-muted">{label}</span>
      <span className="text-[14px] font-mono text-push-text">{value}</span>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ArrangementView({
  filePath: initialFilePath = '',
  genre: initialGenre = 'organic house',
  bpm: initialBpm,
}: ArrangementViewProps) {
  const [filePath, setFilePath] = useState(initialFilePath)
  const [genre, setGenre] = useState(initialGenre)
  const [bpm, setBpm] = useState<number | ''>(initialBpm ?? '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ArrangementResult | null>(null)

  const inputClass =
    'bg-push-elevated border border-push-border rounded-[3px] ' +
    'text-[11px] text-push-text px-2 py-1 ' +
    'placeholder:text-push-muted ' +
    'focus:outline-none focus:border-push-orange transition-colors'

  const handleAnalyze = async () => {
    if (!filePath.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const params: Record<string, unknown> = {
        file_path: filePath.trim(),
        genre,
        duration: 300,
      }
      if (bpm !== '') params.bpm = Number(bpm)

      const response = await mcpClient.callTool({
        name: 'analyze_arrangement',
        params,
      })

      if (!response.success) {
        throw new Error(response.error ?? 'Tool call failed')
      }

      setResult(response.data as ArrangementResult)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full bg-push-bg text-push-text">

      {/* ── Input bar ──────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-push-border flex-shrink-0 flex-wrap">
        <input
          type="text"
          className={`${inputClass} flex-1 min-w-[180px]`}
          value={filePath}
          onChange={e => setFilePath(e.target.value)}
          placeholder="/path/to/mix.wav"
          spellCheck={false}
          onKeyDown={e => { if (e.key === 'Enter') { void handleAnalyze() } }}
        />
        <select
          className={inputClass}
          value={genre}
          onChange={e => setGenre(e.target.value)}
          style={{ minWidth: '130px' }}
        >
          {SUPPORTED_GENRES.map(g => (
            <option key={g} value={g}>{g}</option>
          ))}
        </select>
        <input
          type="number"
          className={`${inputClass} w-20`}
          value={bpm}
          onChange={e => setBpm(e.target.value === '' ? '' : Number(e.target.value))}
          placeholder="BPM"
          min={60}
          max={200}
        />
        <button
          onClick={() => { void handleAnalyze() }}
          disabled={loading || !filePath.trim()}
          className="px-3 py-1 rounded-[3px] border border-push-orange text-push-orange
                     text-[10px] uppercase tracking-[0.06em]
                     hover:bg-push-orange hover:text-push-bg
                     disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? '…' : 'Analyze'}
        </button>
      </div>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">

        {/* Idle state */}
        {!loading && !error && !result && (
          <div className="flex flex-col items-center justify-center h-40 gap-2">
            <div className="text-[10px] text-push-muted">
              Enter a file path and click Analyze
            </div>
            <div className="text-[9px] text-push-muted opacity-60">
              Visualizes sections, energy curve, and arrangement problems
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && <LoadingSpinner />}

        {/* Error */}
        {!loading && error && (
          <div className="p-4 flex flex-col gap-2">
            <span className="text-[10px] text-push-red">{error}</span>
            <button
              onClick={() => { void handleAnalyze() }}
              className="self-start px-3 py-1 rounded-[3px] border border-push-orange text-push-orange
                         text-[10px] uppercase tracking-[0.06em]
                         hover:bg-push-orange hover:text-push-bg transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Result */}
        {!loading && result && (
          <div className="p-3 flex flex-col gap-4">

            {/* Score + timeline header row */}
            <div className="flex items-start gap-3">
              <div className="flex-1">
                <SectionLabel>Section Timeline</SectionLabel>
                <SectionTimeline
                  sections={result.sections}
                  totalDuration={result.total_duration_sec}
                />
              </div>
              <ScoreBadge score={result.arrangement_score} />
            </div>

            {/* Energy Curve */}
            <div>
              <SectionLabel>Energy Curve (dBFS)</SectionLabel>
              <div className="border border-push-border rounded-[3px] overflow-hidden bg-push-surface">
                <EnergyCurve
                  sections={result.sections}
                  totalDuration={result.total_duration_sec}
                />
              </div>
            </div>

            {/* Problems */}
            <div>
              <SectionLabel>
                Problems ({result.problems.length})
              </SectionLabel>
              <ArrangementProblemsList problems={result.problems} />
            </div>

            {/* Energy flow stats */}
            <div>
              <SectionLabel>Energy Flow</SectionLabel>
              <EnergyFlowStats flow={result.energy_flow} />
            </div>

          </div>
        )}
      </div>
    </div>
  )
}
