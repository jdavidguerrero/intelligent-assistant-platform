import clsx from 'clsx'
import { Fader } from '../common/Fader'
import type { Track, TrackType } from '../../types/ableton'
import { abletonWs } from '../../services/abletonWs'
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
  const color = typeColor(track.type)
  const faderValue = dbToFader(track.volume_db)

  function toggleMute() {
    if (track.lom_path) {
      abletonWs.setProperty(track.lom_path, 'mute', track.mute ? 0 : 1)
    }
  }

  function toggleSolo() {
    if (track.lom_path) {
      abletonWs.setProperty(track.lom_path, 'solo', track.solo ? 0 : 1)
    }
  }

  function toggleArm() {
    if (track.lom_path) {
      abletonWs.setProperty(track.lom_path, 'arm', track.arm ? 0 : 1)
    }
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
          style={{ color: track.mute ? '#444' : '#D4D4D4' }}
        >
          {track.name}
        </span>

        {/* Device count badge */}
        {track.device_count > 0 && (
          <span
            className="push-label shrink-0"
            style={{ color: '#444', minWidth: 16, textAlign: 'right' }}
          >
            {track.device_count}
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
