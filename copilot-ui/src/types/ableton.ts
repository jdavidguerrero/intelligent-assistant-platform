// Types mirroring core/ableton/types.py + lom_scanner.js wire format.
// Optional fields exist in both shapes so either source can populate the interface.

export interface Parameter {
  name: string
  value: number
  // Python API fields
  min_value?: number
  max_value?: number
  default_value?: number
  display_value?: string
  // lom_scanner.js wire fields
  min?: number
  max?: number
  default?: number
  display?: string
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
  length_bars?: number   // Python API
  length?: number        // lom_scanner wire format (beats)
  is_playing: boolean
  is_triggered: boolean
  is_midi: boolean
  lom_path: string
  color?: number
  slot_index?: number    // lom_scanner wire format
}

export type TrackType = 'audio' | 'midi' | 'return' | 'master' | 'group'

export interface Track {
  name: string
  index: number
  type: TrackType
  arm: boolean
  solo: boolean
  mute: boolean
  volume_db?: number     // Python API (dB scale)
  volume?: number        // lom_scanner wire format (0–1 raw)
  pan?: number
  device_count?: number  // Python API
  device_names?: string[] // Python API
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
  // Python API uses a single string; lom_scanner sends numerator + denominator separately
  time_signature?: string
  time_sig_numerator?: number
  time_sig_denominator?: number
  is_playing: boolean
  scene_count: number
  track_count?: number
  current_song_time?: number
  metronome?: boolean
  loop?: boolean
  session_record?: boolean
  overdub?: boolean
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
  | { type: 'call_method'; lom_path: string; method: string; args?: (string | number)[]; id?: string }
  | { type: 'ping' }
