import { useSessionStore } from '../../store/sessionStore'
import { useAnalysisStore } from '../../store/analysisStore'
import { Badge } from '../common/Badge'
import { SUPPORTED_GENRES } from '../../types/analysis'

export function Header() {
  const { session, wsStatus, lastPingMs } = useSessionStore()
  const { genre, setGenre } = useAnalysisStore()

  const tempo = session?.tempo ?? 0
  // Support both Python API (time_signature string) and lom_scanner (separate numerator/denominator)
  const timeSig =
    session?.time_signature ??
    (session
      ? `${session.time_sig_numerator ?? 4}/${session.time_sig_denominator ?? 4}`
      : '4/4')
  const isPlaying = session?.is_playing ?? false
  // Support both Python API (track_count) and lom_scanner (tracks array length)
  const trackCount = session?.track_count ?? session?.tracks.length ?? 0

  return (
    <header
      className="flex items-center justify-between px-4 shrink-0 border-b"
      style={{
        height: 44,
        backgroundColor: '#1A1A1A',
        borderColor: '#2E2E2E',
      }}
    >
      {/* Left: wordmark */}
      <div className="flex items-center gap-3">
        <span
          className="text-sm font-semibold tracking-widest uppercase"
          style={{ color: '#FF7700', letterSpacing: '0.2em' }}
        >
          COPILOT
        </span>
        <span className="push-label" style={{ color: '#444' }}>|</span>
        {trackCount > 0 && (
          <span className="push-label" style={{ color: '#555' }}>{trackCount} TRACKS</span>
        )}
      </div>

      {/* Center: transport */}
      <div className="flex items-center gap-4">
        {/* Play indicator */}
        <div className="flex items-center gap-2">
          <div
            className="rounded-sm"
            style={{
              width: 8,
              height: 8,
              backgroundColor: isPlaying ? '#7EB13D' : '#444',
              boxShadow: isPlaying ? '0 0 6px #7EB13D88' : 'none',
            }}
          />
          <span
            className="push-number"
            style={{ fontSize: 16, letterSpacing: '0.05em', minWidth: 80 }}
          >
            {tempo > 0 ? tempo.toFixed(1) : '---'}
          </span>
          <span className="push-label">BPM</span>
        </div>
        <span className="push-number" style={{ color: '#555' }}>{timeSig}</span>
      </div>

      {/* Right: genre selector + WS status */}
      <div className="flex items-center gap-3">
        <select
          value={genre}
          onChange={(e) => setGenre(e.target.value)}
          className="text-[11px] uppercase tracking-wider rounded px-2 py-1 border outline-none"
          style={{
            backgroundColor: '#222222',
            borderColor: '#2E2E2E',
            color: '#FFFFFF',
            fontFamily: 'inherit',
          }}
        >
          {SUPPORTED_GENRES.map((g) => (
            <option key={g} value={g}>
              {g.toUpperCase()}
            </option>
          ))}
        </select>

        <div className="flex items-center gap-2">
          <Badge variant="status" value={wsStatus} />
          {wsStatus === 'connected' && lastPingMs != null && (
            <span className="push-label" style={{ color: '#444' }}>
              {lastPingMs}ms
            </span>
          )}
        </div>
      </div>
    </header>
  )
}
