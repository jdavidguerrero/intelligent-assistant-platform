import { create } from 'zustand'
import type { MixReport } from '../types/analysis'

type AnalysisStatus = 'idle' | 'loading' | 'success' | 'error'

interface AnalysisStore {
  report: MixReport | null
  status: AnalysisStatus
  error: string | null
  filePath: string
  genre: string
  duration: number
  setFilePath: (path: string) => void
  setGenre: (genre: string) => void
  setDuration: (duration: number) => void
  setReport: (report: MixReport) => void
  setStatus: (status: AnalysisStatus, error?: string) => void
  clearReport: () => void
}

export const useAnalysisStore = create<AnalysisStore>((set) => ({
  report: null,
  status: 'idle',
  error: null,
  filePath: '',
  genre: 'organic house',
  duration: 180,
  setFilePath: (filePath) => set({ filePath }),
  setGenre: (genre) => set({ genre }),
  setDuration: (duration) => set({ duration }),
  setReport: (report) => set({ report, status: 'success', error: null }),
  setStatus: (status, error = undefined) => set({ status, error: error ?? null }),
  clearReport: () => set({ report: null, status: 'idle', error: null }),
}))
