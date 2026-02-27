/**
 * auditStore — stores the latest audit report findings indexed by channel_name.
 * Updated whenever AuditWorkflow completes an audit.
 */

import { create } from 'zustand'
import type { AuditFinding } from '../services/mcpClient'

interface AuditStore {
  /** Map from channel_name → worst severity for that channel */
  channelSeverity: Record<string, string>
  /** All findings from the last audit */
  findings: AuditFinding[]
  setFindings: (findings: AuditFinding[]) => void
  clearFindings: () => void
}

function worstSeverity(findings: AuditFinding[], channelName: string): string {
  const ORDER: Record<string, number> = { critical: 0, warning: 1, info: 2, suggestion: 3 }
  const matching = findings.filter(f => f.channel_name === channelName)
  if (matching.length === 0) return ''
  return matching.reduce((best, f) =>
    (ORDER[f.severity] ?? 9) < (ORDER[best.severity] ?? 9) ? f : best
  ).severity
}

export const useAuditStore = create<AuditStore>((set) => ({
  channelSeverity: {},
  findings: [],
  setFindings: (findings) => {
    const names = [...new Set(findings.map(f => f.channel_name))]
    const channelSeverity: Record<string, string> = {}
    for (const name of names) {
      channelSeverity[name] = worstSeverity(findings, name)
    }
    set({ findings, channelSeverity })
  },
  clearFindings: () => set({ findings: [], channelSeverity: {} }),
}))
