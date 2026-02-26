import { useEffect } from 'react'
import { abletonWs } from '../services/abletonWs'
import { useSessionStore } from '../store/sessionStore'

export function useAbletonSession() {
  const { setSession, applyParameterDelta, setWsStatus, setLastPingMs } = useSessionStore()

  useEffect(() => {
    // Subscribe to service events and bridge to store
    const unsub1 = abletonWs.onSessionState(setSession)
    const unsub2 = abletonWs.onParameterDelta(({ lom_path, value, display }) =>
      applyParameterDelta(lom_path, value, display)
    )
    const unsub3 = abletonWs.onStatusChange(({ status, error }) =>
      setWsStatus(status, error)
    )
    const unsub4 = abletonWs.onPong(setLastPingMs)

    // Connect (singleton — won't reconnect if already connected)
    if (abletonWs.status === 'disconnected') {
      abletonWs.connect()
    } else {
      // Sync current status to store on mount
      setWsStatus(abletonWs.status)
    }

    return () => {
      unsub1()
      unsub2()
      unsub3()
      unsub4()
    }
  }, [setSession, applyParameterDelta, setWsStatus, setLastPingMs])

  const { session, wsStatus, wsError, lastPingMs, selectedTrackIndex, selectTrack } =
    useSessionStore()

  return {
    session,
    wsStatus,
    wsError,
    lastPingMs,
    selectedTrackIndex,
    selectTrack,
    connect: () => abletonWs.connect(),
    disconnect: () => abletonWs.disconnect(),
    refreshSession: () => abletonWs.getSession(),
    setParameter: (lomPath: string, value: number) =>
      abletonWs.setParameter(lomPath, value),
    setProperty: (lomPath: string, property: string, value: number | string) =>
      abletonWs.setProperty(lomPath, property, value),
  }
}
