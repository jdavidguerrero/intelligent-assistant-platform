/**
 * SpectrumAnalyzer — 7-band spectrum display with genre target overlays.
 *
 * Shows SUB/LOW/LMD/MID/HMD/HGH/AIR bands colored by deviation from genre target.
 * Deviation: ≤2dB=green, 2-4dB=yellow, >4dB=red.
 */

import { SpectrumBar } from '../common/SpectrumBar'
import type { SpectralData, BandProfile } from '../../types/analysis'
import { GENRE_TARGETS, BAND_LABELS } from '../../types/analysis'

interface Props {
  spectral: SpectralData
  genre: string
}

export function SpectrumAnalyzer({ spectral, genre }: Props) {
  const targets = GENRE_TARGETS[genre] ?? GENRE_TARGETS['organic house']
  const bands = spectral.bands

  const bandKeys = Object.keys(BAND_LABELS) as Array<keyof BandProfile>

  return (
    <div className="p-3 space-y-3">
      <div className="text-[9px] uppercase tracking-[0.08em] text-push-muted">
        Spectrum
      </div>

      {/* 7 bands */}
      <div className="flex items-end gap-1 justify-between h-28">
        {bandKeys.map((key) => {
          const measured = bands[key]
          const target = targets[key]
          const label = BAND_LABELS[key]
          return (
            <SpectrumBar
              key={key}
              value={measured}
              target={target}
              label={label.short}
              rangeLabel={label.range}
            />
          )
        })}
      </div>

      {/* Centroid + Tilt */}
      <div className="flex gap-4 text-[10px] font-mono text-push-muted border-t border-push-border pt-2">
        <span>
          Centroid:{' '}
          <span className="text-push-text">
            {spectral.spectral_centroid_hz?.toFixed(0) ?? '—'} Hz
          </span>
        </span>
        <span>
          Tilt:{' '}
          <span className="text-push-text">
            {spectral.spectral_tilt_db_oct != null
              ? `${spectral.spectral_tilt_db_oct > 0 ? '+' : ''}${spectral.spectral_tilt_db_oct.toFixed(1)} dB/oct`
              : '—'}
          </span>
        </span>
        {spectral.overall_rms_db != null && (
          <span>
            RMS:{' '}
            <span className="text-push-text">
              {spectral.overall_rms_db.toFixed(1)} dB
            </span>
          </span>
        )}
      </div>
    </div>
  )
}
