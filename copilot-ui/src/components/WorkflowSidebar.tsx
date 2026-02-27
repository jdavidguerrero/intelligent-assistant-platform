/**
 * WorkflowSidebar — narrow vertical strip between the Session panel and
 * the center content area.  Shows 5 workflow buttons + a Home button.
 *
 * Clicking a workflow sets it active (orange border + label).
 * Clicking the active workflow or Home returns to the Analysis Dashboard.
 */

import { useWorkflowStore, WORKFLOWS, type WorkflowId } from '../store/workflowStore'

export function WorkflowSidebar() {
  const { activeWorkflow, setWorkflow } = useWorkflowStore()

  function toggle(id: WorkflowId) {
    setWorkflow(activeWorkflow === id ? null : id)
  }

  return (
    <div
      className="flex-shrink-0 border-r border-push-border bg-push-bg flex flex-col items-center py-1 gap-0.5"
      style={{ width: '44px' }}
    >
      {/* Home button — returns to Analysis Dashboard */}
      <button
        onClick={() => setWorkflow(null)}
        title="Analysis Dashboard"
        className={`
          w-9 h-9 rounded-[3px] flex flex-col items-center justify-center gap-0.5
          transition-colors duration-100 border
          ${activeWorkflow === null
            ? 'border-push-orange text-push-orange bg-push-orange/10'
            : 'border-transparent text-push-muted hover:text-push-text hover:border-push-border'}
        `}
      >
        <span className="text-[13px] leading-none">⊙</span>
        <span className="text-[7px] uppercase tracking-[0.04em] leading-none">Home</span>
      </button>

      <div className="w-6 border-t border-push-border my-0.5" />

      {/* Workflow buttons */}
      {WORKFLOWS.map((wf) => (
        <button
          key={wf.id}
          onClick={() => toggle(wf.id)}
          title={wf.description}
          className={`
            w-9 h-9 rounded-[3px] flex flex-col items-center justify-center gap-0.5
            transition-colors duration-100 border
            ${activeWorkflow === wf.id
              ? 'border-push-orange text-push-orange bg-push-orange/10'
              : 'border-transparent text-push-muted hover:text-push-text hover:border-push-border'}
          `}
        >
          <span className="text-[13px] leading-none">{wf.icon}</span>
          <span className="text-[7px] uppercase tracking-[0.04em] leading-none">{wf.label}</span>
        </button>
      ))}
    </div>
  )
}
