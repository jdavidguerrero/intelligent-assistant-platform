import { create } from 'zustand'
import type { SessionSummary, WsStatus } from '../types/ableton'

interface SessionStore {
  session: SessionSummary | null
  wsStatus: WsStatus
  wsError: string | null
  lastPingMs: number | null
  selectedTrackIndex: number | null
  setSession: (session: SessionSummary) => void
  applyParameterDelta: (lomPath: string, value: number, display: string) => void
  applyTrackProperty: (
    trackIndex: number,
    isReturn: boolean,
    property: 'arm' | 'solo' | 'mute',
    value: boolean
  ) => void
  setWsStatus: (status: WsStatus, error?: string) => void
  setLastPingMs: (ms: number) => void
  selectTrack: (index: number | null) => void
  clearSession: () => void
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  session: null,
  wsStatus: 'disconnected',
  wsError: null,
  lastPingMs: null,
  selectedTrackIndex: null,

  setSession: (session) => set({ session }),

  applyTrackProperty: (trackIndex, isReturn, property, value) => {
    const session = get().session
    if (!session) return
    const patch = (tracks: SessionSummary['tracks']) =>
      tracks.map((t, i) => (i === trackIndex ? { ...t, [property]: value } : t))
    set({
      session: {
        ...session,
        tracks:        isReturn ? session.tracks        : patch(session.tracks),
        return_tracks: isReturn ? patch(session.return_tracks) : session.return_tracks,
      },
    })
  },

  applyParameterDelta: (lomPath, value, _display) => {
    const session = get().session
    if (!session) return
    // Update the parameter value in the relevant track/device
    const updated: SessionSummary = {
      ...session,
      tracks: session.tracks.map((track) => ({
        ...track,
        devices: track.devices?.map((device) => ({
          ...device,
          parameters: device.parameters?.map((param) =>
            param.lom_path === lomPath ? { ...param, value } : param
          ),
        })),
      })),
    }
    set({ session: updated })
  },

  setWsStatus: (wsStatus, wsError = undefined) => set({ wsStatus, wsError: wsError ?? null }),
  setLastPingMs: (lastPingMs) => set({ lastPingMs }),
  selectTrack: (selectedTrackIndex) => set({ selectedTrackIndex }),
  clearSession: () => set({ session: null, selectedTrackIndex: null }),
}))
