// Types mirroring core/ableton/types.py — the Python source of truth

export interface Parameter {
  name: string
  value: number
  min_value: number
  max_value: number
  default_value: number
  display_value: string
  lom_path: string
  index: number
  is_quantized: boolean
}

export interface Device {
  name: string
  class_name: string
  is_active: boolean
  parameters?: Parameter[]
  lom_path: string
  index: number
}

export interface Clip {
  name: string
  length_bars: number
  is_playing: boolean
  is_triggered: boolean
  is_midi: boolean
  lom_path: string
  color?: number
}

export type TrackType = 'audio' | 'midi' | 'return' | 'master' | 'group'

export interface Track {
  name: string
  index: number
  type: TrackType
  arm: boolean
  solo: boolean
  mute: boolean
  volume_db: number
  pan?: number
  device_count: number
  device_names: string[]
  devices?: Device[]
  clips?: Clip[]
  lom_path?: string
  color?: number
}

export interface SessionSummary {
  tracks: Track[]
  return_tracks: Track[]
  master_track: Track | null
  tempo: number
  time_signature: string
  is_playing: boolean
  scene_count: number
  track_count: number
}

// WebSocket message types
export type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

export type WsIncoming =
  | { type: 'session_state'; data: SessionSummary }
  | { type: 'parameter_delta'; data: { lom_path: string; value: number; display: string } }
  | { type: 'ack'; lom_path: string; value: number; id?: string }
  | { type: 'pong'; ts: number }
  | { type: 'error'; message: string; id?: string }

export type WsOutgoing =
  | { type: 'get_session' }
  | { type: 'set_parameter'; lom_path: string; value: number; id?: string }
  | { type: 'set_property'; lom_path: string; property: string; value: number | string; id?: string }
  | { type: 'ping' }
