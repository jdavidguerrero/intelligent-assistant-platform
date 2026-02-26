/**
 * ProblemsList — Sorted list of mix problems with FIX buttons.
 *
 * FIX button pre-fills chat input (does NOT call tool directly).
 * Routes through /ask so Claude confirms params before executing.
 */

import { Badge } from '../common/Badge'
import type { MixProblem, Recommendation } from '../../types/analysis'
import { useChatStore } from '../../store/chatStore'

interface Props {
  problems: MixProblem[]
  recommendations?: Recommendation[]
}

export function ProblemsList({ problems, recommendations = [] }: Props) {
  const setPendingInput = useChatStore((s) => s.setPendingInput)

  // Sort by severity descending
  const sorted = [...problems].sort((a, b) => b.severity - a.severity)

  function handleFix(problem: MixProblem) {
    // Find matching recommendation by category
    const rec = recommendations.find(
      (r) => r.problem_category === problem.category
    )
    const query = rec?.rag_query
      ?? `How do I fix "${problem.category}" in my mix? ${problem.description}`

    setPendingInput(query)

    // Focus the chat panel
    window.dispatchEvent(new CustomEvent('copilot:focus-chat'))
  }

  if (sorted.length === 0) {
    return (
      <div className="p-3">
        <div className="text-[9px] uppercase tracking-[0.08em] text-push-muted mb-2">
          Problems
        </div>
        <div className="text-[10px] text-push-muted italic">
          No problems detected
        </div>
      </div>
    )
  }

  return (
    <div className="p-3 space-y-2">
      <div className="text-[9px] uppercase tracking-[0.08em] text-push-muted">
        Problems ({sorted.length})
      </div>

      <div className="space-y-1">
        {sorted.map((problem, idx) => (
          <div
            key={idx}
            className="flex items-start gap-2 p-2 rounded-[3px] bg-push-surface border border-push-border"
          >
            {/* Severity badge */}
            <Badge variant="severity" value={problem.severity} />

            {/* Problem info */}
            <div className="flex-1 min-w-0 space-y-0.5">
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-push-orange font-medium truncate">
                  {problem.category}
                </span>
                {problem.frequency_range_hz && (
                  <span className="text-[9px] text-push-muted shrink-0">
                    {problem.frequency_range_hz[0]}–{problem.frequency_range_hz[1]} Hz
                  </span>
                )}
              </div>
              <div className="text-[10px] text-push-muted line-clamp-2">
                {problem.description}
              </div>
            </div>

            {/* FIX button */}
            <button
              onClick={() => handleFix(problem)}
              className="
                shrink-0 px-2 py-0.5 rounded-[2px] border text-[9px] uppercase tracking-[0.08em]
                border-push-orange text-push-orange
                hover:bg-push-orange hover:text-push-bg
                transition-colors duration-100
              "
            >
              Fix
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
