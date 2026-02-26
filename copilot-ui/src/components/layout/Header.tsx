import { useSessionStore } from '../../store/sessionStore'
import { useAnalysisStore } from '../../store/analysisStore'
import { Badge } from '../common/Badge'
import { SUPPORTED_GENRES } from '../../types/analysis'
import { abletonWs } from '../../services/abletonWs'

/* ── Transport button ─────────────────────────────────────────────────── */
interface TBtnProps {
  active?: boolean
  activeColor?: string
  onClick: () => void
  title: string
  children: React.ReactNode
  disabled?: boolean
}

function TBtn({ active, activeColor = '#FF7700', onClick, title, children, disabled }: TBtnProps) {
  return (
    <button
      title={title}
      disabled={disabled}
      onClick={onClick}
      className="flex items-center justify-center rounded-sm select-none transition-colors"
      style={{
        width: 26,
        height: 22,
        fontSize: 11,
        border: `1px solid ${active ? activeColor : '#2E2E2E'}`,
        backgroundColor: active ? `${activeColor}22` : 'transparent',
        color: active ? activeColor : '#666',
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.4 : 1,
      }}
      onMouseEnter={(e) => {
        if (!disabled && !active) {
          ;(e.currentTarget as HTMLButtonElement).style.borderColor = '#444'
          ;(e.currentTarget as HTMLButtonElement).style.color = '#FFFFFF'
        }
      }}
      onMouseLeave={(e) => {
        ;(e.currentTarget as HTMLButtonElement).style.borderColor = active ? activeColor : '#2E2E2E'
        ;(e.currentTarget as HTMLButtonElement).style.color = active ? activeColor : '#666'
      }}
    >
      {children}
    </button>
  )
}

/* ── Header ───────────────────────────────────────────────────────────── */
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
  const isPlaying      = session?.is_playing     ?? false
  const isLooping      = session?.loop            ?? false
  const isMetronome    = session?.metronome       ?? false
  const isRecording    = session?.session_record  ?? false
  const isOverdub      = session?.overdub         ?? false
  // Support both Python API (track_count) and lom_scanner (tracks array length)
  const trackCount = session?.track_count ?? session?.tracks.length ?? 0

  const connected = wsStatus === 'connected'

  /* ── Transport actions ─────────────────────────────────────────────── */
  function handleBackToStart() {
    abletonWs.setProperty('live_set', 'current_song_time', 0)
  }

  function handlePlayStop() {
    if (isPlaying) {
      abletonWs.callMethod('live_set', 'stop_playing')
    } else {
      abletonWs.callMethod('live_set', 'start_playing')
    }
  }

  function handleContinue() {
    abletonWs.callMethod('live_set', 'continue_playing')
  }

  function handleRecord() {
    abletonWs.setProperty('live_set', 'session_record', isRecording ? 0 : 1)
  }

  function handleLoop() {
    abletonWs.setProperty('live_set', 'loop', isLooping ? 0 : 1)
  }

  function handleMetronome() {
    abletonWs.setProperty('live_set', 'metronome', isMetronome ? 0 : 1)
  }

  function handleOverdub() {
    abletonWs.setProperty('live_set', 'overdub', isOverdub ? 0 : 1)
  }

  return (
    <header
      className="flex items-center justify-between px-4 shrink-0 border-b"
      style={{
        height: 44,
        backgroundColor: '#1A1A1A',
        borderColor: '#2E2E2E',
      }}
    >
      {/* Left: wordmark + track count */}
      <div className="flex items-center gap-3" style={{ minWidth: 120 }}>
        <span
          className="text-sm font-semibold tracking-widest uppercase"
          style={{ color: '#FF7700', letterSpacing: '0.2em' }}
        >
          COPILOT
        </span>
        <span className="push-label" style={{ color: '#333' }}>|</span>
        {trackCount > 0 && (
          <span className="push-label" style={{ color: '#555' }}>{trackCount} TRK</span>
        )}
      </div>

      {/* Center: full transport bar */}
      <div className="flex items-center gap-1">

        {/* Tempo display */}
        <div
          className="flex items-center gap-1.5 px-2 mr-2 rounded"
          style={{ border: '1px solid #2E2E2E', height: 22 }}
        >
          <div
            className="rounded-full"
            style={{
              width: 6,
              height: 6,
              backgroundColor: isPlaying ? '#7EB13D' : '#333',
              boxShadow: isPlaying ? '0 0 5px #7EB13D88' : 'none',
              transition: 'all 0.15s',
            }}
          />
          <span
            className="push-number"
            style={{ fontSize: 14, letterSpacing: '0.04em', minWidth: 50, color: '#FFFFFF' }}
          >
            {tempo > 0 ? tempo.toFixed(2) : '---.--'}
          </span>
          <span className="push-label" style={{ color: '#444' }}>BPM</span>
          <span
            className="push-number"
            style={{ fontSize: 11, color: '#555', marginLeft: 6 }}
          >
            {timeSig}
          </span>
        </div>

        {/* ◀◀ Back to start */}
        <TBtn title="Back to start" onClick={handleBackToStart} disabled={!connected}>
          ◀◀
        </TBtn>

        {/* ▶ / ■  Play / Stop */}
        <TBtn
          title={isPlaying ? 'Stop' : 'Play'}
          active={isPlaying}
          activeColor="#7EB13D"
          onClick={handlePlayStop}
          disabled={!connected}
        >
          {isPlaying ? '■' : '▶'}
        </TBtn>

        {/* ▶| Continue */}
        <TBtn title="Continue playing" onClick={handleContinue} disabled={!connected}>
          ▶|
        </TBtn>

        {/* separator */}
        <span style={{ width: 1, height: 16, backgroundColor: '#2E2E2E', margin: '0 4px' }} />

        {/* ⏺ Session Record */}
        <TBtn
          title="Session Record"
          active={isRecording}
          activeColor="#E53935"
          onClick={handleRecord}
          disabled={!connected}
        >
          ●
        </TBtn>

        {/* ⊕ Overdub */}
        <TBtn
          title="Overdub"
          active={isOverdub}
          activeColor="#E53935"
          onClick={handleOverdub}
          disabled={!connected}
        >
          ⊕
        </TBtn>

        {/* separator */}
        <span style={{ width: 1, height: 16, backgroundColor: '#2E2E2E', margin: '0 4px' }} />

        {/* ↺ Loop */}
        <TBtn
          title="Arrangement Loop"
          active={isLooping}
          activeColor="#FF7700"
          onClick={handleLoop}
          disabled={!connected}
        >
          ↺
        </TBtn>

        {/* ♩ Metronome */}
        <TBtn
          title="Metronome"
          active={isMetronome}
          activeColor="#FF7700"
          onClick={handleMetronome}
          disabled={!connected}
        >
          ♩
        </TBtn>
      </div>

      {/* Right: genre selector + WS status */}
      <div className="flex items-center gap-3" style={{ minWidth: 240, justifyContent: 'flex-end' }}>
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
