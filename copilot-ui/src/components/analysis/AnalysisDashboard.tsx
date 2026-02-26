/**
 * AnalysisDashboard — Main analysis panel orchestrator.
 *
 * Layout:
 *   AnalysisFileInput (always visible)
 *   → loading spinner while analyzing
 *   → SpectrumAnalyzer + [StereoMeter + LoudnessMeter] + ProblemsList
 */

import { useAudioAnalysis } from '../../hooks/useAudioAnalysis'
import { AnalysisFileInput } from './AnalysisFileInput'
import { SpectrumAnalyzer } from './SpectrumAnalyzer'
import { StereoMeter } from './StereoMeter'
import { LoudnessMeter } from './LoudnessMeter'
import { ProblemsList } from './ProblemsList'

export function AnalysisDashboard() {
  const { report, status, genre } = useAudioAnalysis()

  return (
    <div className="flex flex-col h-full">
      {/* File input row — always visible */}
      <AnalysisFileInput />

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {status === 'loading' && (
          <div className="flex flex-col items-center justify-center h-40 gap-3">
            {/* Spinner */}
            <div className="w-6 h-6 rounded-full border-2 border-push-border border-t-push-orange animate-spin" />
            <span className="text-[10px] text-push-muted">Analyzing audio…</span>
          </div>
        )}

        {status === 'idle' && (
          <div className="flex flex-col items-center justify-center h-40 gap-2">
            <div className="text-[10px] text-push-muted">
              Enter a server file path and click Analyze
            </div>
            <div className="text-[9px] text-push-muted opacity-60">
              Supports .wav, .mp3, .flac, .aiff
            </div>
          </div>
        )}

        {(status === 'success' || status === 'error') && report && (
          <div className="divide-y divide-push-border">
            {/* Spectrum */}
            <SpectrumAnalyzer spectral={report.spectral} genre={genre} />

            {/* Stereo + Loudness side by side */}
            <div className="grid grid-cols-2 divide-x divide-push-border">
              {report.stereo ? (
                <StereoMeter stereo={report.stereo} />
              ) : (
                <div className="p-3 text-[10px] text-push-muted">
                  No stereo data
                </div>
              )}
              <LoudnessMeter dynamics={report.dynamics} />
            </div>

            {/* Problems list */}
            <ProblemsList
              problems={report.problems}
              recommendations={report.recommendations}
            />

            {/* Footer: genre + duration */}
            <div className="px-3 py-2 flex gap-4 text-[9px] text-push-muted">
              <span>Genre: <span className="text-push-text">{report.genre}</span></span>
              {report.duration_sec != null && (
                <span>
                  Duration:{' '}
                  <span className="text-push-text">
                    {report.duration_sec.toFixed(1)}s
                  </span>
                </span>
              )}
              {report.sample_rate != null && (
                <span>
                  SR: <span className="text-push-text">{report.sample_rate} Hz</span>
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
