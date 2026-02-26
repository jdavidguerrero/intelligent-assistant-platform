export type MessageRole = 'user' | 'assistant' | 'system'
export type ResponseMode = 'rag' | 'tool' | 'degraded'

export interface SourceReference {
  index: number
  source_name: string
  source_path: string
  page_number: number | null
  score: number
}

export interface ToolCallRecord {
  tool_name: string
  params: Record<string, unknown>
  success: boolean
  error: string | null
  data_summary?: Record<string, unknown>
}

export interface UsageMetadata {
  input_tokens?: number
  output_tokens?: number
  total_tokens?: number
  total_ms?: number
  model?: string
  cache_hit?: boolean
}

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  timestamp: number
  mode?: ResponseMode
  sources?: SourceReference[]
  citations?: number[]
  tool_calls?: ToolCallRecord[]
  usage?: UsageMetadata
  isStreaming?: boolean
  error?: string
}

export interface ActionCard {
  id: string
  label: string
  description: string
  query: string
}

export const QUICK_ACTIONS: ActionCard[] = [
  {
    id: 'read-session',
    label: 'Read Session',
    description: 'Show all Ableton tracks and devices',
    query: 'What tracks do I have in my Ableton session?',
  },
  {
    id: 'mix-advice',
    label: 'Mix Advice',
    description: 'Get AI mix feedback from current analysis',
    query: 'Give me specific mix feedback based on the detected problems',
  },
  {
    id: 'chord-suggest',
    label: 'Chord Ideas',
    description: 'Suggest a chord progression',
    query: 'Suggest a chord progression for organic house in A minor',
  },
  {
    id: 'mastering-check',
    label: 'Mastering',
    description: 'Check master bus readiness',
    query: 'What mastering issues should I address in my current mix?',
  },
]
