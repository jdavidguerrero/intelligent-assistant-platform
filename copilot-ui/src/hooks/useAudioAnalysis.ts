import { useAnalysisStore } from '../store/analysisStore'
import { mcpClient, McpError } from '../services/mcpClient'

export function useAudioAnalysis() {
  const { report, status, error, filePath, genre, duration,
    setFilePath, setGenre, setDuration, setReport, setStatus } = useAnalysisStore()

  async function analyze() {
    if (!filePath.trim()) {
      setStatus('error', 'Please enter a file path')
      return
    }
    setStatus('loading')
    try {
      const result = await mcpClient.analyzeMix({ file_path: filePath, genre, duration })
      setReport(result)
    } catch (err) {
      const msg = err instanceof McpError
        ? err.detail
        : err instanceof Error ? err.message : 'Unknown error'
      setStatus('error', msg)
    }
  }

  return { report, status, error, filePath, genre, duration,
    setFilePath, setGenre, setDuration, analyze }
}
