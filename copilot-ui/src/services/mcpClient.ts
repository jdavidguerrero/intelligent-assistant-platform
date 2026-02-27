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

export interface AuditFinding {
  layer: string
  severity: string
  icon: string
  channel_name: string
  channel_lom_path: string
  device_name: string | null
  rule_id: string
  message: string
  reason: string
  confidence: number
  fix_action: { lom_path: string; lom_id?: number; property: string; value: number | string } | null
}

export interface AuditReport {
  generated_at: number
  critical_count: number
  warning_count: number
  suggestion_count: number
  info_count: number
  findings: AuditFinding[]
  session_map: {
    buses: Array<{ name: string; bus_type: string; channel_count: number; channels: string[] }>
    orphan_channel_count: number
    return_channel_count: number
    total_channels: number
    mapped_at: number
  }
}

export interface PatternsResponse {
  sessions_saved: number
  patterns: Record<string, {
    sample_count: number
    volume_db_values: number[]
    has_hp_values: boolean[]
    hp_freq_values: number[]
    comp_ratio_values: number[]
  }>
}

export interface SavePatternsResponse {
  channels_learned: number
  sessions_saved: number
}

export interface ApplyFixRequest {
  lom_path: string
  lom_id?: number
  property: string
  value: number | string
  description?: string
}

// ── Master / Reference types ───────────────────────────────────────────────

export interface MasterReport {
  readiness_score: number
  genre: string
  loudness: {
    lufs_integrated: number
    true_peak_db: number
    inter_sample_peaks: boolean
  }
  dynamics: {
    crest_factor_db: number
  }
  issues: string[]
  mastering_chain: {
    genre: string
    stage: string
    description: string
    processors: Array<{
      name: string
      proc_type: string
      plugin_primary: string
      plugin_fallback?: string
      params: Array<{ name: string; value: string }>
    }>
  }
}

export interface ComparisonReport {
  overall_similarity: number
  lufs_delta: number
  lufs_normalization_db: number
  num_references: number
  dimensions: Array<{
    name: string
    score: number
    track_value: number | null
    ref_value: number | null
    unit?: string
  }>
  deltas: Array<{
    dimension: string
    direction: string
    magnitude: number
    unit?: string
    priority: number
    recommendation: string
  }>
  band_deltas?: Array<{
    band: string
    track_db: number
    reference_db: number
    delta_db: number
  }>
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

  async auditSession(req: { genre_preset?: string | null; force_refresh?: boolean }): Promise<AuditReport> {
    return request('/session/audit', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  },

  async getPatterns(): Promise<PatternsResponse> {
    return request('/session/patterns')
  },

  async savePatterns(): Promise<SavePatternsResponse> {
    return request('/session/patterns/save', { method: 'POST', body: '{}' })
  },

  async applyFix(req: ApplyFixRequest): Promise<{ applied: boolean; lom_path: string; ack: unknown }> {
    return request('/session/apply-fix', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  },

  async analyzeMaster(req: { file_path: string; genre?: string }): Promise<MasterReport> {
    return request('/mix/master', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  },

  async compareReference(req: {
    file_path: string
    reference_paths: string[]
    genre?: string
  }): Promise<ComparisonReport> {
    return request('/mix/reference', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  },
}
