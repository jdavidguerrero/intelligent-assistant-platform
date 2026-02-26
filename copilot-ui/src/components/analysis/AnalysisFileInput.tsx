/**
 * AnalysisFileInput — Server-side file path + genre selector + Analyze button.
 *
 * The file_path is an ABSOLUTE path on the server filesystem (not a browser upload).
 */

import { useAudioAnalysis } from '../../hooks/useAudioAnalysis'
import { SUPPORTED_GENRES } from '../../types/analysis'

export function AnalysisFileInput() {
  const { filePath, genre, status, error, setFilePath, setGenre, analyze } = useAudioAnalysis()
  const isLoading = status === 'loading'

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') analyze()
  }

  return (
    <div className="p-3 border-b border-push-border space-y-2">
      {/* Label */}
      <div className="text-[9px] uppercase tracking-[0.08em] text-push-muted">
        Audio File Path (server absolute)
      </div>

      {/* File path input */}
      <input
        type="text"
        value={filePath}
        onChange={(e) => setFilePath(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="/path/to/bounce.wav"
        disabled={isLoading}
        className="
          w-full bg-push-surface border border-push-border rounded-[3px]
          px-2 py-1 font-mono text-[11px] text-push-text
          placeholder-push-muted
          focus:outline-none focus:border-push-orange
          disabled:opacity-50
        "
      />

      {/* Genre + Analyze row */}
      <div className="flex items-center gap-2">
        <select
          value={genre}
          onChange={(e) => setGenre(e.target.value)}
          disabled={isLoading}
          className="
            bg-push-surface border border-push-border rounded-[3px]
            px-2 py-1 text-[10px] text-push-text
            focus:outline-none focus:border-push-orange
            disabled:opacity-50
            flex-1
          "
        >
          {SUPPORTED_GENRES.map((g) => (
            <option key={g} value={g}>{g}</option>
          ))}
        </select>

        <button
          onClick={analyze}
          disabled={isLoading || !filePath.trim()}
          className="
            px-3 py-1 rounded-[3px] border text-[10px] uppercase tracking-[0.08em]
            border-push-orange text-push-orange
            hover:bg-push-orange hover:text-push-bg
            disabled:opacity-40 disabled:cursor-not-allowed
            transition-colors duration-150
            flex-shrink-0
          "
        >
          {isLoading ? 'Analyzing…' : 'Analyze'}
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div className="text-[10px] text-push-red px-1">
          {error}
        </div>
      )}
    </div>
  )
}
