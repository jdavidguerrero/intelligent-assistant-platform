/**
 * StemAnalysisView — Per-stem analysis panel.
 *
 * Renders a grid of stem cards, each with:
 *   - Header: track name + stem type badge (color-coded by type)
 *   - Frequency footprint: 7-band mini bar chart (sub/low/low_mid/mid/high_mid/high/air)
 *   - Problems list: severity badge + category name
 *   - Footer: RMS dBFS | LUFS | Crest factor
 *
 * Compact mode: just name + stem type badge + problem count.
 *
 * Used standalone and embedded inside AutoSetupWizard step 3.
 */

// No React import needed — JSX transform handles it automatically

// ── Types (exported so AutoSetupWizard can import them) ───────────────────────

export interface StemProblem {
  category: string
  severity: number
  description: string
}

export interface StemFootprint {
  bands: Record<string, number>   // 0-1 relative energy per band
  dominant_bands: string[]
  rms_db: number
  crest_factor_db: number
}

export interface StemDynamics {
  rms_db: number
  lufs: number
  crest_factor_db: number
}

export interface StemData {
  track_name: string
  stem_type: string
  problems: StemProblem[]
  footprint: StemFootprint | null
  dynamics: StemDynamics
}

export interface ContributionData {
  stem_name: string
  percentage: number
}

export interface StemAnalysisViewProps {
  stems: StemData[]
  attribution?: Record<string, ContributionData[]>
  compact?: boolean
}

// ── Constants ─────────────────────────────────────────────────────────────────

const STEM_TYPE_COLORS: Record<string, string> = {
  kick:       '#ef4444',
  bass:       '#f97316',
  pad:        '#8b5cf6',
  percussion: '#eab308',
  vocal:      '#22c55e',
  fx:         '#06b6d4',
  unknown:    '#6b7280',
}

// Ordered 7 bands matching the BandProfile key order
const BAND_ORDER = ['sub', 'low', 'low_mid', 'mid', 'high_mid', 'high', 'air']
const BAND_SHORT: Record<string, string> = {
  sub:      'SUB',
  low:      'LOW',
  low_mid:  'LMD',
  mid:      'MID',
  high_mid: 'HMD',
  high:     'HGH',
  air:      'AIR',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function stemColor(stemType: string): string {
  return STEM_TYPE_COLORS[stemType.toLowerCase()] ?? STEM_TYPE_COLORS['unknown']
}

function severityColor(severity: number): string {
  if (severity >= 7) return '#E53935'
  if (severity >= 4) return '#E5C020'
  return '#7EB13D'
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StemTypeBadge({ stemType }: { stemType: string }) {
  const color = stemColor(stemType)
  return (
    <span
      className="px-1.5 py-0.5 rounded-[3px] text-[8px] uppercase tracking-[0.06em] font-bold flex-shrink-0"
      style={{ border: `1px solid ${color}`, color }}
    >
      {stemType}
    </span>
  )
}

function SeverityBadge({ severity }: { severity: number }) {
  const color = severityColor(severity)
  return (
    <span
      className="px-1.5 py-0.5 rounded-[3px] text-[9px] font-mono flex-shrink-0"
      style={{ border: `1px solid ${color}`, color }}
    >
      {severity}
    </span>
  )
}

interface FrequencyBarsProps {
  bands: Record<string, number>
  dominantBands: string[]
}

function FrequencyBars({ bands, dominantBands }: FrequencyBarsProps) {
  const dominant = new Set(dominantBands)
  return (
    <div className="flex items-end gap-0.5 h-8">
      {BAND_ORDER.map(band => {
        const value = bands[band] ?? 0
        const isDominant = dominant.has(band)
        const heightPercent = Math.max(4, Math.round(value * 100))
        return (
          <div key={band} className="flex flex-col items-center flex-1 gap-0.5">
            <div
              className="w-full rounded-[1px] flex-shrink-0"
              style={{
                height: `${heightPercent}%`,
                background: isDominant ? '#FF7700' : '#3A3A3A',
                minHeight: '2px',
              }}
            />
            <span
              className="text-[6px] font-mono leading-none"
              style={{ color: isDominant ? '#FF7700' : '#555555' }}
            >
              {BAND_SHORT[band] ?? band}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ── Full stem card ────────────────────────────────────────────────────────────

function StemCard({ stem }: { stem: StemData }) {
  const { track_name, stem_type, problems, footprint, dynamics } = stem

  return (
    <div
      className="bg-push-surface border border-push-border rounded-[4px] p-3 flex flex-col gap-2"
    >
      {/* Header: name + type badge */}
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-push-text font-medium flex-1 truncate">
          {track_name}
        </span>
        <StemTypeBadge stemType={stem_type} />
      </div>

      {/* Frequency footprint bar chart */}
      {footprint !== null ? (
        <FrequencyBars
          bands={footprint.bands}
          dominantBands={footprint.dominant_bands}
        />
      ) : (
        <div
          className="h-8 flex items-center justify-center text-[9px] text-push-muted italic"
        >
          No footprint data
        </div>
      )}

      {/* Problems list */}
      {problems.length > 0 ? (
        <div className="flex flex-col gap-1">
          {problems.map((p, i) => (
            <div key={i} className="flex items-center gap-2">
              <SeverityBadge severity={p.severity} />
              <span className="text-[9px] text-push-muted uppercase tracking-[0.04em] truncate">
                {p.category}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <span className="text-[9px] text-push-green">No problems</span>
      )}

      {/* Footer: metrics */}
      <div
        className="flex items-center gap-2 pt-1 border-t border-push-border text-[9px] font-mono text-push-muted"
      >
        <span>{dynamics.rms_db.toFixed(1)} dBFS</span>
        <span className="text-push-border">|</span>
        <span>{dynamics.lufs.toFixed(1)} LUFS</span>
        <span className="text-push-border">|</span>
        <span>CF {dynamics.crest_factor_db.toFixed(1)} dB</span>
      </div>
    </div>
  )
}

// ── Compact stem card ─────────────────────────────────────────────────────────

function StemCardCompact({ stem }: { stem: StemData }) {
  const { track_name, stem_type, problems } = stem
  return (
    <div
      className="bg-push-surface border border-push-border rounded-[3px] px-2 py-1.5
                 flex items-center gap-2"
    >
      <span className="text-[10px] text-push-text flex-1 truncate">{track_name}</span>
      <StemTypeBadge stemType={stem_type} />
      {problems.length > 0 && (
        <span
          className="text-[8px] font-mono px-1 py-0.5 rounded-[2px] flex-shrink-0"
          style={{
            background: 'rgba(229,57,53,0.15)',
            color: '#E53935',
            border: '1px solid rgba(229,57,53,0.4)',
          }}
        >
          {problems.length}
        </span>
      )}
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────

export default function StemAnalysisView({
  stems,
  compact = false,
}: StemAnalysisViewProps) {
  if (stems.length === 0) {
    return (
      <div className="p-4 text-[10px] text-push-muted italic">No stems detected.</div>
    )
  }

  if (compact) {
    return (
      <div className="flex flex-col gap-1">
        {stems.map((stem, i) => (
          <StemCardCompact key={i} stem={stem} />
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-2 p-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}>
      {stems.map((stem, i) => (
        <StemCard key={i} stem={stem} />
      ))}
    </div>
  )
}
