/**
 * PatternInsights — "How you usually work" dashboard.
 *
 * Fetches /session/patterns and renders per-instrument-type stats:
 *   - Sample count + confidence bar
 *   - Median volume, HP freq, and comp ratio with inline sparkline
 *   - Layer 2 activation status (needs 3+ saved sessions)
 *
 * Usage:
 *   <PatternInsights />                 — loads and shows own data
 *   <PatternInsights autoLoad={false} /> — waits for parent to call refresh
 */

import { useState, useEffect, useCallback } from 'react'
import { mcpClient } from '../services/mcpClient'
import type { PatternsResponse } from '../services/mcpClient'

// ── helpers ────────────────────────────────────────────────────────────────

function median(values: number[]): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0
    ? ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2
    : (sorted[mid] ?? 0)
}

function confidenceLevel(sampleCount: number): { pct: number; label: string; cls: string } {
  const pct = Math.min(sampleCount / 10, 1) * 100
  if (sampleCount >= 10) return { pct, label: 'High', cls: 'bg-push-green' }
  if (sampleCount >= 5)  return { pct, label: 'Medium', cls: 'bg-push-yellow' }
  return { pct, label: 'Low', cls: 'bg-push-orange' }
}

// ── sub-components ─────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[9px] uppercase tracking-[0.08em] text-push-muted block mb-1">
      {children}
    </span>
  )
}

interface StatRowProps {
  label: string
  value: string
}
function StatRow({ label, value }: StatRowProps) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[9px] text-push-muted">{label}</span>
      <span className="text-[10px] font-mono text-push-text">{value}</span>
    </div>
  )
}

interface MiniBarProps {
  pct: number
  cls: string
}
function MiniBar({ pct, cls }: MiniBarProps) {
  return (
    <div className="relative h-1 bg-push-border rounded-full mt-0.5 mb-1">
      <div
        className={`absolute left-0 top-0 h-full rounded-full ${cls}`}
        style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
      />
    </div>
  )
}

interface InstrumentCardProps {
  name: string
  data: PatternsResponse['patterns'][string]
}
function InstrumentCard({ name, data }: InstrumentCardProps) {
  const conf = confidenceLevel(data.sample_count)
  const medVol = median(data.volume_db_values)
  const hpActive = data.has_hp_values.filter(Boolean).length
  const hpPct = data.has_hp_values.length > 0
    ? Math.round((hpActive / data.has_hp_values.length) * 100)
    : 0
  const medHp = median(data.hp_freq_values.filter(v => v > 0))
  const medComp = median(data.comp_ratio_values.filter(v => v > 0))

  return (
    <div className="bg-push-surface border border-push-border rounded-[3px] p-3 flex flex-col gap-2">
      {/* Header: name + confidence */}
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-push-text font-medium uppercase tracking-[0.04em] truncate">
          {name}
        </span>
        <span className="text-[9px] text-push-muted flex-shrink-0">
          {data.sample_count} samples
        </span>
      </div>

      {/* Confidence bar */}
      <div>
        <div className="flex items-center justify-between mb-0.5">
          <span className="text-[8px] text-push-muted uppercase tracking-[0.06em]">Confidence</span>
          <span className="text-[8px] text-push-muted">{conf.label}</span>
        </div>
        <MiniBar pct={conf.pct} cls={conf.cls} />
      </div>

      {/* Stats */}
      <div className="flex flex-col gap-0.5">
        <StatRow label="Avg Volume" value={`${medVol.toFixed(1)} dB`} />
        {medHp > 0 && (
          <StatRow label={`HP Filter (${hpPct}% of tracks)`} value={`${Math.round(medHp)} Hz`} />
        )}
        {medComp > 0 && (
          <StatRow label="Comp Ratio" value={`${medComp.toFixed(1)}:1`} />
        )}
      </div>
    </div>
  )
}

// ── Layer 2 status banner ──────────────────────────────────────────────────

function Layer2Banner({ sessionsSaved }: { sessionsSaved: number }) {
  const active = sessionsSaved >= 3
  return (
    <div
      className={`
        flex items-center gap-2 px-3 py-2 rounded-[3px] border
        ${active
          ? 'border-push-green bg-green-900/10'
          : 'border-push-border bg-push-surface'}
      `}
    >
      <span className="text-[11px]">{active ? '✓' : '⏳'}</span>
      <div className="flex flex-col gap-0.5 flex-1 min-w-0">
        <span className="text-[10px] text-push-text">
          {active ? 'Layer 2 Active — Pattern Anomaly Detection' : 'Layer 2 Inactive'}
        </span>
        <span className="text-[9px] text-push-muted">
          {active
            ? `${sessionsSaved} sessions learned · anomalies detected with MAD`
            : `${sessionsSaved}/3 sessions saved — save more sessions to activate`}
        </span>
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

interface PatternInsightsProps {
  /** If true (default), fetches patterns on mount. Set to false to control externally. */
  autoLoad?: boolean
  /** Compact mode for embedding inside AuditWorkflow. */
  compact?: boolean
}

export function PatternInsights({ autoLoad = true, compact = false }: PatternInsightsProps) {
  const [data, setData] = useState<PatternsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await mcpClient.getPatterns()
      setData(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load patterns')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (autoLoad) void load()
  }, [autoLoad, load])

  const instrumentNames = data ? Object.keys(data.patterns) : []

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 text-push-muted">
        <div className="w-3 h-3 rounded-full border border-push-border border-t-push-orange animate-spin flex-shrink-0" />
        <span className="text-[10px]">Loading patterns…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-between gap-2 px-3 py-2 bg-push-surface border border-push-border rounded-[3px]">
        <span className="text-[10px] text-push-red truncate">{error}</span>
        <button
          onClick={() => void load()}
          className="text-[9px] text-push-muted hover:text-push-text uppercase tracking-[0.06em] flex-shrink-0"
        >
          Retry
        </button>
      </div>
    )
  }

  if (!data) return null

  const hasPatterns = instrumentNames.length > 0

  return (
    <div className={`flex flex-col gap-3 ${compact ? '' : 'p-4'}`}>
      {!compact && (
        <div>
          <h3 className="text-[11px] text-push-text font-medium mb-0.5">Pattern History</h3>
          <p className="text-[10px] text-push-muted leading-relaxed">
            Your learned mixing style — accumulated across {data.sessions_saved} saved sessions.
          </p>
        </div>
      )}

      {/* Layer 2 status */}
      <Layer2Banner sessionsSaved={data.sessions_saved} />

      {/* Per-instrument cards */}
      {hasPatterns ? (
        <div>
          <SectionLabel>Instrument Patterns ({instrumentNames.length} types)</SectionLabel>
          <div className="flex flex-col gap-2">
            {instrumentNames.map(name => (
              <InstrumentCard key={name} name={name} data={data.patterns[name]!} />
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-push-surface border border-push-border rounded-[3px] p-3">
          <span className="text-[10px] text-push-muted">
            No patterns learned yet. Save sessions from the Audit workflow to build your profile.
          </span>
        </div>
      )}

      {!compact && (
        <button
          onClick={() => void load()}
          className="self-start text-[9px] text-push-muted hover:text-push-text uppercase tracking-[0.06em]"
        >
          ↺ Refresh
        </button>
      )}
    </div>
  )
}
