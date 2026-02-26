/**
 * LoudnessMeter — LUFS + peak dBFS + crest factor display.
 *
 * Large LUFS number colored by loudness zone:
 *   < -20 LUFS: blue (too quiet)
 *   -20 to -10: green (good zone)
 *   -10 to -6:  yellow (borderline)
 *   > -6:       red (too loud)
 */

import type { DynamicsData } from '../../types/analysis'

interface Props {
  dynamics: DynamicsData
}

function lufsColor(lufs: number): string {
  if (lufs < -20) return '#5B9BD5' // too quiet — blue
  if (lufs <= -10) return '#3D8D40' // good — green
  if (lufs <= -6)  return '#B5A020' // borderline — yellow
  return '#E53935'                  // too loud — red
}

function lufsLabel(lufs: number): string {
  if (lufs < -20) return 'Too Quiet'
  if (lufs <= -10) return 'Good'
  if (lufs <= -6)  return 'Loud'
  return 'Clipping Risk'
}

export function LoudnessMeter({ dynamics }: Props) {
  const color = lufsColor(dynamics.lufs)
  const label = lufsLabel(dynamics.lufs)

  // Map LUFS -40..0 to 0-100% for bar
  const lufsBarPct = Math.max(0, Math.min(100, ((dynamics.lufs + 40) / 40) * 100))

  return (
    <div className="p-3 space-y-3">
      <div className="text-[9px] uppercase tracking-[0.08em] text-push-muted">
        Loudness
      </div>

      {/* Large LUFS display */}
      <div className="flex items-baseline gap-2">
        <span className="font-mono leading-none" style={{ fontSize: '28px', color }}>
          {dynamics.lufs.toFixed(1)}
        </span>
        <div className="space-y-0.5">
          <div className="text-[9px] text-push-muted">LUFS</div>
          <div className="text-[9px]" style={{ color }}>{label}</div>
        </div>
      </div>

      {/* Loudness bar with target zone */}
      <div className="h-2 bg-push-elevated rounded-[2px] overflow-hidden relative">
        {/* Target zone highlight (-10 to -6 LUFS = 75% to 85%) */}
        <div
          className="absolute top-0 bottom-0 opacity-20"
          style={{ left: '75%', right: '15%', backgroundColor: '#3D8D40' }}
        />
        <div
          className="h-full rounded-[2px] transition-all"
          style={{ width: `${lufsBarPct}%`, backgroundColor: color }}
        />
      </div>
      <div className="flex justify-between text-[8px] text-push-muted">
        <span>-40</span>
        <span>-20</span>
        <span>-10</span>
        <span>0</span>
      </div>

      {/* Peak + Crest */}
      <div className="flex gap-4 text-[10px] font-mono border-t border-push-border pt-2">
        <div className="space-y-0.5">
          <div className="text-[9px] text-push-muted">Peak</div>
          <div className={dynamics.peak_db > -1 ? 'text-push-red' : 'text-push-text'}>
            {dynamics.peak_db.toFixed(1)} dBFS
          </div>
        </div>
        {dynamics.crest_factor_db != null && (
          <div className="space-y-0.5">
            <div className="text-[9px] text-push-muted">Crest</div>
            <div className="text-push-text">
              {dynamics.crest_factor_db.toFixed(1)} dB
            </div>
          </div>
        )}
        {dynamics.dynamic_range_db != null && (
          <div className="space-y-0.5">
            <div className="text-[9px] text-push-muted">DR</div>
            <div className="text-push-text">
              {dynamics.dynamic_range_db.toFixed(1)} dB
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
