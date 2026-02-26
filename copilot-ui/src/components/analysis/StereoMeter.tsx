/**
 * StereoMeter — Stereo width + correlation display.
 *
 * Width bar: 0-100% (shows mono/stereo balance)
 * Correlation bar: -1 to +1 (negative=red, <0.3=yellow, ≥0.3=green)
 */

import type { StereoData } from '../../types/analysis'

interface Props {
  stereo: StereoData
}

function correlationColor(cor: number): string {
  if (cor < 0) return '#E53935'
  if (cor < 0.3) return '#B5A020'
  return '#3D8D40'
}

export function StereoMeter({ stereo }: Props) {
  const widthPct = Math.max(0, Math.min(100, stereo.width))
  // Correlation is -1 to +1; map to 0-100% for the bar
  const corPct = Math.max(0, Math.min(100, ((stereo.lr_correlation + 1) / 2) * 100))
  const corColor = correlationColor(stereo.lr_correlation)

  return (
    <div className="p-3 space-y-3">
      <div className="text-[9px] uppercase tracking-[0.08em] text-push-muted">
        Stereo
      </div>

      {/* Width bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-[9px] text-push-muted">
          <span>Width</span>
          <span className="font-mono text-push-text">{widthPct.toFixed(0)}%</span>
        </div>
        <div className="h-2 bg-push-elevated rounded-[2px] overflow-hidden">
          <div
            className="h-full rounded-[2px] transition-all"
            style={{ width: `${widthPct}%`, backgroundColor: '#FF7700' }}
          />
        </div>
      </div>

      {/* Correlation bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-[9px] text-push-muted">
          <span>Correlation</span>
          <span className="font-mono text-push-text"
            style={{ color: corColor }}>
            {stereo.lr_correlation.toFixed(2)}
          </span>
        </div>
        <div className="h-2 bg-push-elevated rounded-[2px] overflow-hidden">
          {/* Center line at 50% */}
          <div className="relative h-full">
            <div
              className="absolute h-full rounded-[2px] transition-all"
              style={{ width: `${corPct}%`, backgroundColor: corColor }}
            />
          </div>
        </div>
        <div className="flex justify-between text-[8px] text-push-muted">
          <span>-1</span>
          <span>0</span>
          <span>+1</span>
        </div>
      </div>

      {/* Mid/Side ratio if present */}
      {stereo.mid_side_ratio_db != null && (
        <div className="text-[10px] font-mono text-push-muted">
          M/S:{' '}
          <span className="text-push-text">
            {stereo.mid_side_ratio_db > 0 ? '+' : ''}
            {stereo.mid_side_ratio_db.toFixed(1)} dB
          </span>
        </div>
      )}
    </div>
  )
}
