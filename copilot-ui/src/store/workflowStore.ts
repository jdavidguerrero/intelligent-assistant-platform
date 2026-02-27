/**
 * workflowStore — active workflow selection + first-run onboarding flag.
 *
 * null = show the default Analysis Dashboard (no workflow active).
 * Any WorkflowId = the named guided workflow is displayed in the center panel.
 *
 * onboardingDone persists to localStorage so the modal only appears once.
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type WorkflowId =
  | 'compose'
  | 'mix'
  | 'master'
  | 'reference'
  | 'perform'
  | 'autosetup'
  | 'arrange'
  | 'versions'
  | 'audit'

export interface WorkflowMeta {
  id: WorkflowId
  label: string
  icon: string
  description: string
}

export const WORKFLOWS: WorkflowMeta[] = [
  { id: 'compose',   icon: '♪', label: 'Compose',   description: 'Generate chords, bass & drums' },
  { id: 'mix',       icon: '⊞', label: 'Mix',        description: 'Diagnose & fix your mix' },
  { id: 'master',    icon: '◎', label: 'Master',     description: 'Mastering readiness check' },
  { id: 'reference', icon: '⇄', label: 'Reference',  description: 'Compare to commercial tracks' },
  { id: 'perform',   icon: '▶', label: 'Perform',    description: 'Live session monitoring' },
  { id: 'autosetup', icon: '◈', label: 'Setup',      description: 'Auto-setup stems & parameters' },
  { id: 'arrange',   icon: '≋', label: 'Arrange',    description: 'Section detection & energy flow' },
  { id: 'versions',  icon: '⊘', label: 'Versions',   description: 'Mix version history & comparison' },
  { id: 'audit',     icon: '⊛', label: 'Audit',      description: 'Session intelligence: 3-layer mix audit' },
]

interface WorkflowStore {
  activeWorkflow: WorkflowId | null
  onboardingDone: boolean
  setWorkflow: (id: WorkflowId | null) => void
  setOnboardingDone: () => void
}

export const useWorkflowStore = create<WorkflowStore>()(
  persist(
    (set) => ({
      activeWorkflow: null,
      onboardingDone: false,
      setWorkflow: (id) => set({ activeWorkflow: id }),
      setOnboardingDone: () => set({ onboardingDone: true }),
    }),
    { name: 'copilot-workflow', partialize: (s) => ({ onboardingDone: s.onboardingDone }) }
  )
)
