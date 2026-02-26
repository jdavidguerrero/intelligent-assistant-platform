import clsx from 'clsx'
import { Fader } from '../common/Fader'
import type { Track, TrackType } from '../../types/ableton'
import { abletonWs } from '../../services/abletonWs'
import { useSessionStore } from '../../store/sessionStore'
import { DevicePanel } from './DevicePanel'

interface TrackStripProps {
  track: Track
  isSelected: boolean
  onSelect: () => void
}

function typeColor(type: TrackType): string {
  switch (type) {
    case 'midi':   return '#3D7EB1'
    case 'audio':  return '#7EB13D'
    case 'return': return '#B5A020'
    case 'master': return '#FF7700'
    case 'group':  return '#9B59B6'
    default:       return '#555'
  }
}

/**
 * Decode Ableton's packed integer color (0xRRGGBB) to a CSS hex string.
 * Falls back to the track-type color when not set or zero.
 */
function abletonColor(raw: number | undefined, fallback: string): string {
  if (!raw || raw === 0) return fallback
  const r = (raw >> 16) & 0xFF
  const g = (raw >> 8)  & 0xFF
  const b =  raw        & 0xFF
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
}

function dbToFader(db: number): number {
  // -60 to +6 dB → 0 to 1
  return Math.max(0, Math.min(1, (db + 60) / 66))
}

function typeIcon(type: TrackType): string {
  switch (type) {
    case 'midi':   return '⬡'
    case 'audio':  return '▶'
    case 'return': return '↩'
    case 'master': return '⊕'
    case 'group':  return '▼'
    default:       return '•'
  }
}

export function TrackStrip({ track, isSelected, onSelect }: TrackStripProps) {
  const applyTrackProperty = useSessionStore((s) => s.applyTrackProperty)
  // Use Ableton's actual track color (packed int) — fallback to type-based color
  const typeFallback = typeColor(track.type)
  const color = abletonColor(track.color, typeFallback)

  // Support both lom_scanner (0-1 linear) and Python API (dB) volume formats
  const faderValue =
    track.volume != null
      ? track.volume                          // lom_scanner: already 0-1
      : track.volume_db != null
        ? dbToFader(track.volume_db)          // Python API: convert dB → 0-1
        : 0.85                                // fallback: 0 dB

  // Support both device_count (Python API) and devices[] array (lom_scanner)
  const deviceCount = track.device_count ?? track.devices?.length ?? 0

  // Return tracks live in the return_tracks list
  const isReturn = track.type === 'return'

  function toggleMute() {
    if (!track.lom_path) return
    const next = !track.mute
    applyTrackProperty(track.index, isReturn, 'mute', next)
    abletonWs.setProperty(track.lom_path, 'mute', next ? 1 : 0)
  }

  function toggleSolo() {
    if (!track.lom_path) return
    const next = !track.solo
    applyTrackProperty(track.index, isReturn, 'solo', next)
    abletonWs.setProperty(track.lom_path, 'solo', next ? 1 : 0)
  }

  function toggleArm() {
    if (!track.lom_path) return
    const next = !track.arm
    applyTrackProperty(track.index, isReturn, 'arm', next)
    abletonWs.setProperty(track.lom_path, 'arm', next ? 1 : 0)
  }

  return (
    <div>
      {/* Track row */}
      <div
        className={clsx(
          'flex items-center px-2 gap-2 cursor-pointer select-none',
          isSelected && 'bg-push-elevated'
        )}
        style={{
          height: 44,
          borderLeft: `2px solid ${color}`,
          borderBottom: '1px solid #1E1E1E',
          backgroundColor: isSelected ? '#222' : 'transparent',
        }}
        onClick={onSelect}
      >
        {/* Type icon */}
        <span style={{ color, fontSize: 10, width: 12, textAlign: 'center' }}>
          {typeIcon(track.type)}
        </span>

        {/* Track name */}
        <span
          className="truncate flex-1 text-[12px]"
          style={{ color: track.mute ? '#555' : '#FFFFFF' }}
        >
          {track.name}
        </span>

        {/* Device count badge */}
        {deviceCount > 0 && (
          <span
            className="push-label shrink-0"
            style={{ color: '#555', minWidth: 16, textAlign: 'right' }}
          >
            {deviceCount}
          </span>
        )}

        {/* Transport buttons */}
        <div className="flex items-center gap-1 shrink-0">
          {track.type !== 'return' && track.type !== 'master' && (
            <button
              className="rounded-sm text-[9px] font-bold w-4 h-4 flex items-center justify-center"
              style={{
                backgroundColor: track.arm ? '#E5393522' : 'transparent',
                color: track.arm ? '#E53935' : '#444',
                border: `1px solid ${track.arm ? '#E5393566' : '#333'}`,
              }}
              onClick={(e) => { e.stopPropagation(); toggleArm() }}
              title="Arm"
            >A</button>
          )}
          <button
            className="rounded-sm text-[9px] font-bold w-4 h-4 flex items-center justify-center"
            style={{
              backgroundColor: track.solo ? '#FF770022' : 'transparent',
              color: track.solo ? '#FF7700' : '#444',
              border: `1px solid ${track.solo ? '#FF770066' : '#333'}`,
            }}
            onClick={(e) => { e.stopPropagation(); toggleSolo() }}
            title="Solo"
          >S</button>
          <button
            className="rounded-sm text-[9px] font-bold w-4 h-4 flex items-center justify-center"
            style={{
              backgroundColor: track.mute ? '#FF770022' : 'transparent',
              color: track.mute ? '#FF7700' : '#444',
              border: `1px solid ${track.mute ? '#FF770066' : '#333'}`,
            }}
            onClick={(e) => { e.stopPropagation(); toggleMute() }}
            title="Mute"
          >M</button>
        </div>

        {/* Volume fader */}
        <Fader value={faderValue} height={28} className="shrink-0" />
      </div>

      {/* Device panel (expanded on click) */}
      {isSelected && <DevicePanel track={track} />}
    </div>
  )
}
