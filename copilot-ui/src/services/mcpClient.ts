import type { MixReport } from '../types/analysis'

const API_BASE = 'http://localhost:8000'

export class McpError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public body: unknown
  ) {
    super(detail)
    this.name = 'McpError'
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json() as { detail?: string }
      detail = typeof body.detail === 'string' ? body.detail : detail
    } catch { /* ignore */ }
    throw new McpError(res.status, detail, null)
  }
  return res.json() as Promise<T>
}

export interface AskRequest {
  query: string
  use_tools?: boolean
  session_id?: string
  temperature?: number
  max_tokens?: number
  top_k?: number
  confidence_threshold?: number
}

export interface AskResponse {
  answer: string
  mode: string
  citations?: number[]
  sources?: unknown[]
  tool_calls?: unknown[]
  usage?: unknown
}

export type StreamEvent =
  | { type: 'step'; step: string }
  | { type: 'chunk'; content: string }
  | { type: 'sources'; sources: unknown[] }
  | { type: 'done'; citations: number[]; usage: Record<string, unknown> }
  | { type: 'error'; code: string; message: string }

export interface ToolCallResponse {
  success: boolean
  data: unknown
  error: string | null
  metadata: Record<string, unknown> | null
}

export const mcpClient = {
  async health(): Promise<{ status: string }> {
    return request('/health')
  },

  async analyzeMix(req: {
    file_path: string
    genre?: string
    duration?: number
  }): Promise<MixReport> {
    return request('/mix/analyze', {
      method: 'POST',
      body: JSON.stringify({
        file_path: req.file_path,
        genre: req.genre ?? 'organic house',
        duration: req.duration ?? 180,
      }),
    })
  },

  async ask(req: AskRequest): Promise<AskResponse> {
    return request('/ask', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  },

  async *askStream(req: AskRequest): AsyncGenerator<StreamEvent> {
    const res = await fetch(`${API_BASE}/ask/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    })

    if (!res.ok || !res.body) {
      let detail = `HTTP ${res.status}`
      try {
        const body = await res.json() as { detail?: string }
        detail = body.detail ?? detail
      } catch { /* ignore */ }
      throw new McpError(res.status, detail, null)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const raw = line.slice(6).trim()
            if (!raw || raw === '[DONE]') continue
            try {
              const event = JSON.parse(raw) as StreamEvent
              yield event
            } catch { /* skip malformed */ }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  },

  async callTool(req: { name: string; params: Record<string, unknown> }): Promise<ToolCallResponse> {
    return request('/tools/call', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  },
}
