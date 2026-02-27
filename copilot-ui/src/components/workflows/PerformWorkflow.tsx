/**
 * PerformWorkflow — Live session monitoring dashboard.
 *
 * NOT a step-by-step workflow. This is a continuous monitoring panel that
 * reads live data from sessionStore (WebSocket-updated) and exposes quick
 * generation / harmonic-mixing helpers via mcpClient.
 *
 * Layout: full-height flex-col, no WorkflowShell wrapper.
 */

import { useState } from 'react'
import { useWorkflowStore } from '../../store/workflowStore'
import { useSessionStore } from '../../store/sessionStore'
import { mcpClient } from '../../services/mcpClient'
import { SUPPORTED_GENRES } from '../../types/analysis'

// ── Harmonic constants ──────────────────────────────────────────────────────

const KEYS = ['Am', 'Cm', 'Dm', 'Em', 'Fm', 'Gm', 'Bm'] as const
type Key = (typeof KEYS)[number]

const MOODS = ['melancholic', 'uplifting', 'dark', 'euphoric'] as const
type Mood = (typeof MOODS)[number]

const BARS_OPTIONS = [4, 8] as const
type Bars = (typeof BARS_OPTIONS)[number]

// Camelot wheel positions for display
const CAMELOT: Record<string, string> = {
  Am: '8A', Cm: '5A', Dm: '7A', Em: '9A', Fm: '4A', Gm: '6A', Bm: '10A',
  'C major': '8B', 'D major': '7B', 'E major': '9B',
  'F major': '5B', 'G major': '6B', 'A major': '11B',
}

// ── Tiny helpers ────────────────────────────────────────────────────────────

function hexColor(raw: number | undefined): string {
  if (raw === undefined) return '#2E2E2E'
  const r = (raw >> 16) & 0xff
  const g = (raw >> 8) & 0xff
  const b = raw & 0xff
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
}

// ── Sub-components ──────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[9px] uppercase tracking-[0.08em] text-push-muted mb-2">
      {children}
    </p>
  )
}

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-push-surface border border-push-border rounded p-3 ${className}`}>
      {children}
    </div>
  )
}

// ── Card 1: Session Status ──────────────────────────────────────────────────

function SessionStatusCard() {
  const session = useSessionStore((s) => s.session)
  const wsStatus = useSessionStore((s) => s.wsStatus)

  const sigNum = session?.time_sig_numerator ?? 4
  const sigDen = session?.time_sig_denominator ?? 4

  return (
    <Card className="col-span-2">
      <SectionLabel>Session Status</SectionLabel>

      <div className="grid grid-cols-2 gap-y-2 gap-x-4">
        {/* Tempo */}
        <div className="flex items-end gap-1">
          <span className="text-[22px] font-mono font-bold text-push-text leading-none">
            {session?.tempo ?? '—'}
          </span>
          <span className="text-[9px] uppercase tracking-[0.06em] text-push-muted mb-[2px]">BPM</span>
        </div>

        {/* Time signature */}
        <div className="flex items-end gap-1">
          <span className="text-[18px] font-mono font-bold text-push-text leading-none">
            {sigNum}/{sigDen}
          </span>
          <span className="text-[9px] uppercase tracking-[0.06em] text-push-muted mb-[2px]">TIME SIG</span>
        </div>

        {/* Playing indicator */}
        <div className="flex items-center gap-1.5">
          <span
            className="w-2 h-2 rounded-full flex-shrink-0"
            style={{ background: session?.is_playing ? '#3D8D40' : '#444' }}
          />
          <span
            className="text-[10px] uppercase tracking-[0.06em] font-medium"
            style={{ color: session?.is_playing ? '#3D8D40' : '#666' }}
          >
            {session?.is_playing ? 'PLAYING' : 'STOPPED'}
          </span>
        </div>

        {/* Track count */}
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-push-muted">
            {session?.tracks.length ?? 0} tracks
          </span>
        </div>

        {/* Loop */}
        <div className="flex items-center gap-1.5">
          <span
            className="w-2 h-2 rounded-full flex-shrink-0"
            style={{ background: session?.loop ? '#FF7700' : '#2E2E2E' }}
          />
          <span className="text-[9px] uppercase tracking-[0.06em] text-push-muted">Loop</span>
        </div>

        {/* Metronome */}
        <div className="flex items-center gap-1.5">
          <span
            className="w-2 h-2 rounded-full flex-shrink-0"
            style={{ background: session?.metronome ? '#FF7700' : '#2E2E2E' }}
          />
          <span className="text-[9px] uppercase tracking-[0.06em] text-push-muted">Metronome</span>
        </div>
      </div>

      {/* WS status pill */}
      <div className="mt-2 flex items-center gap-1">
        <span
          className="text-[8px] uppercase tracking-[0.06em] px-1.5 py-0.5 rounded"
          style={{
            background: wsStatus === 'connected' ? '#1a2e1a' : wsStatus === 'connecting' ? '#2e2a1a' : '#2e1a1a',
            color: wsStatus === 'connected' ? '#3D8D40' : wsStatus === 'connecting' ? '#B5A020' : '#E53935',
          }}
        >
          {wsStatus}
        </span>
        {!session && wsStatus === 'connected' && (
          <span className="text-[9px] text-push-muted">Waiting for session data…</span>
        )}
      </div>
    </Card>
  )
}

// ── Card 2: Active Tracks ───────────────────────────────────────────────────

function ActiveTracksCard() {
  const session = useSessionStore((s) => s.session)

  const activeTracks = (session?.tracks ?? [])
    .filter((t) => t.arm || (t.clips ?? []).some((c) => c.is_playing))
    .slice(0, 6)

  return (
    <Card>
      <SectionLabel>Active Tracks</SectionLabel>

      {activeTracks.length === 0 ? (
        <p className="text-[10px] text-push-muted italic leading-snug">
          No active clips — press play in Ableton
        </p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {activeTracks.map((track, i) => (
            <div key={i} className="flex items-center gap-2 min-w-0">
              <div
                className="w-0.5 h-4 rounded-full flex-shrink-0"
                style={{ background: hexColor(track.color) }}
              />
              <span className="text-[10px] text-push-text truncate flex-1 min-w-0">
                {track.name}
              </span>
              <span
                className="text-[8px] uppercase tracking-[0.04em] px-1 py-0.5 rounded flex-shrink-0"
                style={{ background: '#2E2E2E', color: '#999' }}
              >
                {track.type}
              </span>
              {track.arm && (
                <span
                  className="text-[8px] uppercase tracking-[0.04em] px-1 py-0.5 rounded flex-shrink-0"
                  style={{ background: '#3a1a1a', color: '#E53935' }}
                >
                  ARM
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

// ── Card 3: Quick Generate ──────────────────────────────────────────────────

function QuickGenerateCard() {
  const session = useSessionStore((s) => s.session)

  const [key, setKey] = useState<Key>('Am')
  const [mood, setMood] = useState<Mood>('melancholic')
  const [bars, setBars] = useState<Bars>(4)
  const [genre, setGenre] = useState(SUPPORTED_GENRES[0] ?? 'organic house')

  const [chords, setChords] = useState<string[]>([])
  const [generating, setGenerating] = useState(false)
  const [inserting, setInserting] = useState(false)
  const [insertedOk, setInsertedOk] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleGenerate() {
    setGenerating(true)
    setChords([])
    setInsertedOk(false)
    setError(null)
    try {
      const res = await mcpClient.callTool({
        name: 'suggest_chord_progression',
        params: { key, mood, genre, bars },
      })
      if (!res.success) {
        setError(res.error ?? 'Unknown error')
        return
      }
      const raw = res.data
      if (Array.isArray(raw)) {
        setChords(raw.map(String))
      } else if (typeof raw === 'string') {
        setChords(raw.split(/[\s,]+/).filter(Boolean))
      } else {
        setChords(['—'])
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setGenerating(false)
    }
  }

  async function handleInsert() {
    if (chords.length === 0) return
    setInserting(true)
    setInsertedOk(false)
    setError(null)
    try {
      const res = await mcpClient.callTool({
        name: 'ableton_insert_notes',
        params: { notes: chords.join(' '), bpm: session?.tempo ?? 128 },
      })
      if (!res.success) {
        setError(res.error ?? 'Insert failed')
        return
      }
      setInsertedOk(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Insert failed')
    } finally {
      setInserting(false)
    }
  }

  const selectCls =
    'bg-push-bg border border-push-border rounded text-[10px] text-push-text px-2 py-1 w-full focus:outline-none focus:border-push-orange'

  return (
    <Card>
      <SectionLabel>Quick Generate</SectionLabel>

      <div className="flex flex-col gap-2">
        {/* Key */}
        <div>
          <label className="text-[9px] uppercase tracking-[0.06em] text-push-muted block mb-0.5">Key</label>
          <select value={key} onChange={(e) => setKey(e.target.value as Key)} className={selectCls}>
            {KEYS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>

        {/* Mood */}
        <div>
          <label className="text-[9px] uppercase tracking-[0.06em] text-push-muted block mb-0.5">Mood</label>
          <select value={mood} onChange={(e) => setMood(e.target.value as Mood)} className={selectCls}>
            {MOODS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        {/* Bars */}
        <div>
          <label className="text-[9px] uppercase tracking-[0.06em] text-push-muted block mb-0.5">Bars</label>
          <select value={bars} onChange={(e) => setBars(Number(e.target.value) as Bars)} className={selectCls}>
            {BARS_OPTIONS.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </div>

        {/* Genre */}
        <div>
          <label className="text-[9px] uppercase tracking-[0.06em] text-push-muted block mb-0.5">Genre</label>
          <select value={genre} onChange={(e) => setGenre(e.target.value)} className={selectCls}>
            {SUPPORTED_GENRES.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </div>

        {/* Generate button */}
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="w-full py-1.5 rounded text-[10px] uppercase tracking-[0.06em] border
                     border-push-orange text-push-orange
                     hover:bg-push-orange hover:text-push-bg
                     disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {generating ? '…' : 'Generate Chords'}
        </button>

        {/* Chord result */}
        {chords.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {chords.map((chord, i) => (
              <span
                key={i}
                className="text-[10px] font-mono text-push-orange bg-push-bg border border-push-border px-1.5 py-0.5 rounded"
              >
                {chord}
              </span>
            ))}
          </div>
        )}

        {/* Insert button */}
        {chords.length > 0 && (
          <button
            onClick={handleInsert}
            disabled={inserting}
            className="w-full py-1.5 rounded text-[10px] uppercase tracking-[0.06em] border
                       border-push-green text-push-green
                       hover:bg-push-green hover:text-push-bg
                       disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {inserting ? '…' : insertedOk ? '✓ Inserted' : 'Insert to Ableton'}
          </button>
        )}

        {error && (
          <p className="text-[10px] text-push-red">{error}</p>
        )}
      </div>
    </Card>
  )
}

// ── Card 4: Harmonic Mixing ─────────────────────────────────────────────────

interface CompatibleEntry {
  key: string
  camelot: string
  relationship: 'same' | 'adjacent' | 'relative'
}

function HarmonicMixingCard() {
  const session = useSessionStore((s) => s.session)
  const [key, setKey] = useState<Key>('Am')
  const [results, setResults] = useState<CompatibleEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleFind() {
    setLoading(true)
    setResults([])
    setError(null)
    try {
      const res = await mcpClient.callTool({
        name: 'suggest_compatible_tracks',
        params: { key, bpm: session?.tempo ?? 0 },
      })
      if (!res.success) {
        setError(res.error ?? 'Unknown error')
        return
      }
      // Normalize response: accept array of strings, objects, or a raw string
      const raw = res.data
      let entries: CompatibleEntry[] = []

      if (Array.isArray(raw)) {
        entries = raw.map((item, i): CompatibleEntry => {
          if (typeof item === 'string') {
            const rel: CompatibleEntry['relationship'] =
              i === 0 ? 'same' : i <= 2 ? 'adjacent' : 'relative'
            return { key: item, camelot: CAMELOT[item] ?? '?', relationship: rel }
          }
          const obj = item as Record<string, unknown>
          return {
            key: String(obj.key ?? item),
            camelot: String(obj.camelot ?? CAMELOT[String(obj.key ?? '')] ?? '?'),
            relationship: (obj.relationship as CompatibleEntry['relationship']) ?? 'relative',
          }
        })
      } else if (typeof raw === 'string') {
        entries = raw.split(/[\s,]+/).filter(Boolean).map((k, i): CompatibleEntry => {
          const rel: CompatibleEntry['relationship'] =
            i === 0 ? 'same' : i <= 2 ? 'adjacent' : 'relative'
          return { key: k, camelot: CAMELOT[k] ?? '?', relationship: rel }
        })
      }

      setResults(entries)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  function badgeColor(rel: CompatibleEntry['relationship']) {
    if (rel === 'same') return { bg: '#331a00', text: '#FF7700', border: '#FF7700' }
    if (rel === 'adjacent') return { bg: '#0f2010', text: '#3D8D40', border: '#3D8D40' }
    return { bg: '#2a2600', text: '#B5A020', border: '#B5A020' }
  }

  const selectCls =
    'bg-push-bg border border-push-border rounded text-[10px] text-push-text px-2 py-1 w-full focus:outline-none focus:border-push-orange'

  return (
    <Card>
      <SectionLabel>Harmonic Mixing</SectionLabel>

      <div className="flex flex-col gap-2">
        <div>
          <label className="text-[9px] uppercase tracking-[0.06em] text-push-muted block mb-0.5">Current Key</label>
          <select value={key} onChange={(e) => setKey(e.target.value as Key)} className={selectCls}>
            {KEYS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>

        <button
          onClick={handleFind}
          disabled={loading}
          className="w-full py-1.5 rounded text-[10px] uppercase tracking-[0.06em] border
                     border-push-orange text-push-orange
                     hover:bg-push-orange hover:text-push-bg
                     disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? '…' : 'Find Compatible'}
        </button>

        {results.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {results.map((entry, i) => {
              const c = badgeColor(entry.relationship)
              return (
                <div
                  key={i}
                  className="flex items-center gap-1 px-1.5 py-0.5 rounded border text-[9px] font-mono"
                  style={{ background: c.bg, color: c.text, borderColor: c.border }}
                >
                  <span className="font-bold">{entry.key}</span>
                  <span style={{ color: c.text, opacity: 0.7 }}>{entry.camelot}</span>
                </div>
              )
            })}
          </div>
        )}

        {/* Legend */}
        {results.length > 0 && (
          <div className="flex gap-2 mt-1">
            {(['same', 'adjacent', 'relative'] as const).map((rel) => {
              const c = badgeColor(rel)
              return (
                <div key={rel} className="flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: c.text }} />
                  <span className="text-[8px] uppercase tracking-[0.04em]" style={{ color: c.text }}>
                    {rel}
                  </span>
                </div>
              )
            })}
          </div>
        )}

        {error && <p className="text-[10px] text-push-red">{error}</p>}
      </div>
    </Card>
  )
}

// ── Card 5: Session Notes ───────────────────────────────────────────────────

function SessionNotesCard() {
  const [noteText, setNoteText] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSave() {
    if (!noteText.trim()) return
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      const res = await mcpClient.callTool({
        name: 'create_session_note',
        params: { category: 'discovery', title: 'Session note', content: noteText },
      })
      if (!res.success) {
        setError(res.error ?? 'Save failed')
        return
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="col-span-2">
      <SectionLabel>Session Notes</SectionLabel>

      <textarea
        rows={3}
        value={noteText}
        onChange={(e) => { setNoteText(e.target.value); setSaved(false) }}
        placeholder="Type a note about this session…"
        className="w-full bg-push-bg border border-push-border rounded text-[11px] font-mono
                   text-push-text placeholder:text-push-muted p-2 resize-none
                   focus:outline-none focus:border-push-orange"
      />

      <div className="flex items-center gap-2 mt-2">
        <button
          onClick={handleSave}
          disabled={saving || !noteText.trim()}
          className="px-3 py-1 rounded text-[10px] uppercase tracking-[0.06em] border
                     border-push-orange text-push-orange
                     hover:bg-push-orange hover:text-push-bg
                     disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? '…' : 'Save Note'}
        </button>

        {saved && (
          <span className="text-[10px] text-push-green">✓ Saved</span>
        )}
        {error && (
          <span className="text-[10px] text-push-red">{error}</span>
        )}
      </div>
    </Card>
  )
}

// ── Root component ──────────────────────────────────────────────────────────

export function PerformWorkflow() {
  const setWorkflow = useWorkflowStore((s) => s.setWorkflow)

  return (
    <div className="h-full flex flex-col bg-push-bg">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-push-border flex-shrink-0">
        <span className="text-[11px] uppercase tracking-[0.08em] text-push-orange font-medium">
          ▶ Perform
        </span>
        <button
          onClick={() => setWorkflow(null)}
          className="text-push-muted hover:text-push-text text-[10px] leading-none"
          title="Close"
        >
          ✕
        </button>
      </div>

      {/* Body — 2-column grid */}
      <div className="flex-1 overflow-y-auto p-3 grid grid-cols-2 gap-3">
        <SessionStatusCard />
        <ActiveTracksCard />
        <QuickGenerateCard />
        <HarmonicMixingCard />
        <SessionNotesCard />
      </div>
    </div>
  )
}
