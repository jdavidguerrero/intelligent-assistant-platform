import { Knob } from '../common/Knob'
import type { Track } from '../../types/ableton'
import { abletonWs } from '../../services/abletonWs'
import { useSessionStore } from '../../store/sessionStore'

interface DevicePanelProps {
  track: Track
}

export function DevicePanel({ track }: DevicePanelProps) {
  const { applyParameterDelta } = useSessionStore()

  if (!track.devices || track.devices.length === 0) {
    return (
      <div
        className="px-4 py-3 border-b"
        style={{ backgroundColor: '#111', borderColor: '#1E1E1E' }}
      >
        <span className="push-label" style={{ color: '#444' }}>
          No devices — load with include_parameters=true
        </span>
      </div>
    )
  }

  return (
    <div style={{ backgroundColor: '#111111', borderBottom: '1px solid #1E1E1E' }}>
      {track.devices.map((device) => (
        <div key={device.index} className="px-3 py-2">
          {/* Device header */}
          <div className="flex items-center gap-2 mb-2">
            <div
              className="rounded-sm"
              style={{
                width: 6, height: 6,
                backgroundColor: device.is_active ? '#7EB13D' : '#444',
              }}
            />
            <span className="text-[10px] font-medium" style={{ color: '#D4D4D4' }}>
              {device.name}
            </span>
            <span className="push-label ml-1" style={{ color: '#444' }}>
              {device.class_name}
            </span>
          </div>

          {/* Parameters as knobs */}
          {device.parameters && device.parameters.length > 0 ? (
            <div className="flex gap-3 flex-wrap">
              {device.parameters.slice(0, 8).map((param) => (
                <Knob
                  key={param.index}
                  value={param.value}
                  label={param.name.slice(0, 8)}
                  displayValue={param.display_value ?? param.display ?? ''}
                  size={44}
                  onChange={(newValue) => {
                    // Optimistic update
                    applyParameterDelta(param.lom_path, newValue, param.display_value ?? param.display ?? '')
                    // Send to Ableton
                    abletonWs.setParameter(param.lom_path, newValue)
                  }}
                />
              ))}
            </div>
          ) : (
            <span className="push-label" style={{ color: '#444' }}>
              No parameter data — refresh with include_parameters=true
            </span>
          )}
        </div>
      ))}
    </div>
  )
}
