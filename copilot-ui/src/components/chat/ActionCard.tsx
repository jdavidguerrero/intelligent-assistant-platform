/**
 * ActionCard — Clickable quick-action pill with Push 2 orange style.
 *
 * Orange border at rest → orange fill on hover.
 */

import type { ActionCard as ActionCardType } from '../../types/chat'

interface Props {
  action: ActionCardType
  onClick: (query: string) => void
  disabled?: boolean
}

export function ActionCard({ action, onClick, disabled = false }: Props) {
  return (
    <button
      onClick={() => onClick(action.query)}
      disabled={disabled}
      title={action.description}
      className="
        px-2 py-1 rounded-[3px] border text-[9px] uppercase tracking-[0.08em]
        border-push-orange text-push-orange
        hover:bg-push-orange hover:text-push-bg
        disabled:opacity-40 disabled:cursor-not-allowed
        transition-colors duration-100
        whitespace-nowrap
      "
    >
      {action.label}
    </button>
  )
}
