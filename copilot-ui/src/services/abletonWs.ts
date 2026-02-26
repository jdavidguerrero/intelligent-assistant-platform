import type { SessionSummary, WsIncoming, WsOutgoing, WsStatus } from '../types/ableton'

type Callback<T> = (data: T) => void

class AbletonWsService {
  private static _instance: AbletonWsService | null = null
  private ws: WebSocket | null = null
  private _status: WsStatus = 'disconnected'
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private pingTimestamp = 0
  private reconnectAttempt = 0
  private url = 'ws://localhost:11005'

  // Event subscriber sets
  private onSessionStateCbs = new Set<Callback<SessionSummary>>()
  private onParameterDeltaCbs = new Set<Callback<{ lom_path: string; value: number; display: string }>>()
  private onStatusChangeCbs = new Set<Callback<{ status: WsStatus; error?: string }>>()
  private onPongCbs = new Set<Callback<number>>()

  static getInstance(): AbletonWsService {
    if (!AbletonWsService._instance) {
      AbletonWsService._instance = new AbletonWsService()
    }
    return AbletonWsService._instance
  }

  get status(): WsStatus {
    return this._status
  }

  connect(url = 'ws://localhost:11005'): void {
    this.url = url
    this._doConnect()
  }

  disconnect(): void {
    this._clearTimers()
    this.reconnectAttempt = 0
    if (this.ws) {
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
    }
    this._setStatus('disconnected')
  }

  private _doConnect(): void {
    this._clearTimers()
    this._setStatus('connecting')

    try {
      this.ws = new WebSocket(this.url)
    } catch {
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.reconnectAttempt = 0
      this._setStatus('connected')
      this.send({ type: 'get_session' })
      this._startPing()
    }

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data as string) as WsIncoming
        this._handleMessage(msg)
      } catch {
        // ignore malformed messages
      }
    }

    this.ws.onerror = () => {
      this._setStatus('error', 'WebSocket error')
    }

    this.ws.onclose = () => {
      this._clearTimers()
      if (this._status !== 'disconnected') {
        this._scheduleReconnect()
      }
    }
  }

  private _handleMessage(msg: WsIncoming): void {
    switch (msg.type) {
      case 'session_state':
        this.onSessionStateCbs.forEach((cb) => cb(msg.data))
        break
      case 'parameter_delta':
        this.onParameterDeltaCbs.forEach((cb) => cb(msg.data))
        break
      case 'pong': {
        const latency = Date.now() - this.pingTimestamp
        this.onPongCbs.forEach((cb) => cb(latency))
        break
      }
      case 'error':
        console.warn('[AbletonWs] error from server:', msg.message)
        break
      default:
        break
    }
  }

  private _setStatus(status: WsStatus, error?: string): void {
    this._status = status
    this.onStatusChangeCbs.forEach((cb) => cb({ status, error }))
  }

  private _scheduleReconnect(): void {
    const delays = [1000, 2000, 4000, 8000, 30000]
    const delay = delays[Math.min(this.reconnectAttempt, delays.length - 1)]
    this.reconnectAttempt++
    this._setStatus('disconnected')
    this.reconnectTimer = setTimeout(() => this._doConnect(), delay)
  }

  private _startPing(): void {
    this.pingTimer = setInterval(() => {
      if (this._status === 'connected') {
        this.pingTimestamp = Date.now()
        this.send({ type: 'ping' })
      }
    }, 20000)
  }

  private _clearTimers(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    if (this.pingTimer) clearInterval(this.pingTimer)
    this.reconnectTimer = null
    this.pingTimer = null
  }

  send(msg: WsOutgoing): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  getSession(): void {
    this.send({ type: 'get_session' })
  }

  setParameter(lomPath: string, value: number, id?: string): void {
    this.send({ type: 'set_parameter', lom_path: lomPath, value, id })
  }

  setProperty(lomPath: string, property: string, value: number | string, id?: string): void {
    this.send({ type: 'set_property', lom_path: lomPath, property, value, id })
  }

  callMethod(lomPath: string, method: string, args?: (string | number)[], id?: string): void {
    this.send({ type: 'call_method', lom_path: lomPath, method, args, id })
  }

  // Subscriptions — return unsubscribe function
  onSessionState(cb: Callback<SessionSummary>): () => void {
    this.onSessionStateCbs.add(cb)
    return () => this.onSessionStateCbs.delete(cb)
  }

  onParameterDelta(cb: Callback<{ lom_path: string; value: number; display: string }>): () => void {
    this.onParameterDeltaCbs.add(cb)
    return () => this.onParameterDeltaCbs.delete(cb)
  }

  onStatusChange(cb: Callback<{ status: WsStatus; error?: string }>): () => void {
    this.onStatusChangeCbs.add(cb)
    return () => this.onStatusChangeCbs.delete(cb)
  }

  onPong(cb: Callback<number>): () => void {
    this.onPongCbs.add(cb)
    return () => this.onPongCbs.delete(cb)
  }
}

export const abletonWs = AbletonWsService.getInstance()
