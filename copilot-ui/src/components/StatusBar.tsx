/**
 * StatusBar — bottom strip showing health of all services.
 *
 * Services monitored:
 *   API      — HTTP ping to /health every 10 s
 *   Ableton  — WebSocket status from sessionStore
 *   Session  — whether an Ableton session is loaded (session !== null)
 */

import { useEffect, useState } from 'react'
import { mcpClient } from '../services/mcpClient'
import { useSessionStore } from '../store/sessionStore'

type Health = 'ok' | 'degraded' | 'down' | 'checking'

interface ServiceStatus {
  label: string
  health: Health
  detail?: string
}

function Dot({ health }: { health: Health }) {
  const color =
    health === 'ok'       ? '#3D8D40' :
    health === 'degraded' ? '#B5A020' :
    health === 'down'     ? '#E53935' :
                            '#666666'
  return (
    <span
      style={{ background: color }}
      className="inline-block w-[6px] h-[6px] rounded-full mr-1 flex-shrink-0"
    />
  )
}

function ServicePill({ svc }: { svc: ServiceStatus }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      className="relative flex items-center gap-1 px-2 py-0.5 cursor-default select-none"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <Dot health={svc.health} />
      <span className="text-[9px] uppercase tracking-[0.06em] text-push-muted">{svc.label}</span>
      {hovered && svc.detail && (
        <div className="absolute bottom-full left-0 mb-1 bg-push-elevated border border-push-border
                        rounded-[3px] px-2 py-1 text-[10px] text-push-text whitespace-nowrap z-50 shadow-lg">
          {svc.detail}
        </div>
      )}
    </div>
  )
}

export function StatusBar() {
  const wsStatus  = useSessionStore((s) => s.wsStatus)
  const session   = useSessionStore((s) => s.session)
  const lastPingMs = useSessionStore((s) => s.lastPingMs)

  const [apiHealth, setApiHealth] = useState<Health>('checking')
  const [apiDetail, setApiDetail] = useState<string>()

  // Ping /health every 10 seconds
  useEffect(() => {
    let mounted = true

    async function check() {
      try {
        await mcpClient.health()
        if (mounted) { setApiHealth('ok'); setApiDetail('http://localhost:8000') }
      } catch {
        if (mounted) { setApiHealth('down'); setApiDetail('Cannot reach http://localhost:8000') }
      }
    }

    check()
    const id = setInterval(check, 10_000)
    return () => { mounted = false; clearInterval(id) }
  }, [])

  const wsHealth: Health =
    wsStatus === 'connected'    ? 'ok'       :
    wsStatus === 'connecting'   ? 'degraded' :
    wsStatus === 'disconnected' ? 'down'     : 'down'

  const wsDetail =
    wsStatus === 'connected'  ? `ws://localhost:11005  ${lastPingMs != null ? `${lastPingMs}ms` : ''}` :
    wsStatus === 'connecting' ? 'Connecting to Ableton bridge…' :
                                'ALS Listener not running — load the M4L device'

  const sessionHealth: Health = session ? 'ok' : wsStatus === 'connected' ? 'degraded' : 'down'
  const sessionDetail =
    session
      ? `${session.tracks.length} tracks · ${session.tempo} BPM`
      : wsStatus === 'connected' ? 'No session data yet' : 'Open Ableton with ALS Listener loaded'

  const services: ServiceStatus[] = [
    { label: 'API',     health: apiHealth,     detail: apiDetail },
    { label: 'Bridge',  health: wsHealth,      detail: wsDetail },
    { label: 'Session', health: sessionHealth, detail: sessionDetail },
  ]

  return (
    <div className="flex items-center h-6 border-t border-push-border bg-push-bg px-2 gap-1 flex-shrink-0">
      {services.map((svc) => (
        <ServicePill key={svc.label} svc={svc} />
      ))}
      <div className="flex-1" />
      <span className="text-[9px] text-push-muted px-2 select-none">
        Intelligent Assistant Platform
      </span>
    </div>
  )
}
