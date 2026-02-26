import { useSessionStore } from '../../store/sessionStore'
import { TrackStrip } from './TrackStrip'

export function SessionView() {
  const { session, wsStatus, selectedTrackIndex, selectTrack } = useSessionStore()

  if (wsStatus === 'disconnected' || wsStatus === 'error') {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 p-4">
        <div className="rounded-full" style={{ width: 32, height: 32, backgroundColor: '#2E2E2E', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ color: '#666', fontSize: 16 }}>⚡</span>
        </div>
        <p className="push-label text-center" style={{ color: '#555', maxWidth: 160 }}>
          Connect ALS Listener in Ableton to see your session
        </p>
        <p className="push-label text-center" style={{ color: '#3D8D40' }}>
          ws://localhost:11005
        </p>
      </div>
    )
  }

  if (wsStatus === 'connecting') {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="push-label" style={{ color: '#555' }}>Connecting to Ableton…</span>
      </div>
    )
  }

  if (!session || session.tracks.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="push-label" style={{ color: '#444' }}>No tracks in session</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col overflow-y-auto h-full">
      {/* Session header row */}
      <div
        className="flex items-center px-3 py-1.5 shrink-0"
        style={{ backgroundColor: '#111', borderBottom: '1px solid #2E2E2E' }}
      >
        <span className="push-label" style={{ color: '#444' }}>TRACKS</span>
        <span className="ml-auto push-label" style={{ color: '#444' }}>
          {session.tracks.length + session.return_tracks.length}
        </span>
      </div>

      {/* Regular tracks */}
      {session.tracks.map((track) => (
        <TrackStrip
          key={track.index}
          track={track}
          isSelected={selectedTrackIndex === track.index}
          onSelect={() => selectTrack(selectedTrackIndex === track.index ? null : track.index)}
        />
      ))}

      {/* Return tracks */}
      {session.return_tracks.length > 0 && (
        <>
          <div
            className="flex items-center px-3 py-1"
            style={{ backgroundColor: '#111', borderTop: '1px solid #2E2E2E', borderBottom: '1px solid #2E2E2E' }}
          >
            <span className="push-label" style={{ color: '#444' }}>RETURNS</span>
          </div>
          {session.return_tracks.map((track) => (
            <TrackStrip
              key={`ret-${track.index}`}
              track={track}
              isSelected={false}
              onSelect={() => {}}
            />
          ))}
        </>
      )}
    </div>
  )
}
