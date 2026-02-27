/**
 * GenrePresetPicker — controlled genre-preset selector.
 *
 * Renders a styled <select> with descriptions and an "active preset" chip.
 * Opt-in: "None" means Layer 3 is disabled.
 *
 * Usage:
 *   <GenrePresetPicker value={genre} onChange={setGenre} />
 *   <GenrePresetPicker value={genre} onChange={setGenre} disabled={loading} showDescription />
 */

interface PresetMeta {
  id: string
  label: string
  description: string
  targets: string
}

const PRESETS: PresetMeta[] = [
  {
    id: '',
    label: 'None — Layers 1 + 2 only',
    description: 'Universal rules + your learned patterns. No genre-specific suggestions.',
    targets: '',
  },
  {
    id: 'organic_house',
    label: 'Organic House',
    description: 'Emphasis on warmth, wide stereo pads, sidechain kick-bass relationship.',
    targets: 'LUFS target −8 · HP pads 100–250 Hz · comp ratio 2–4:1',
  },
  {
    id: 'melodic_techno',
    label: 'Melodic Techno',
    description: 'Dense mid-range, dark long-tail reverbs, driving 4/4 groove structures.',
    targets: 'LUFS target −9 · wide synths · kick mono for club systems',
  },
  {
    id: 'deep_house',
    label: 'Deep House',
    description: 'Sub-bass focus, minimal high-freq content, relaxed groove feel.',
    targets: 'LUFS target −10 · bass HP 30–50 Hz · gentle compression',
  },
  {
    id: 'techno',
    label: 'Techno',
    description: 'Maximum headroom, punchy transients, monophonic low end.',
    targets: 'LUFS target −7 · kick mono · tight comp on buses',
  },
]

const selectClass = `
  w-full bg-push-elevated border border-push-border rounded-[3px]
  text-[11px] text-push-text px-2 py-1.5
  focus:outline-none focus:border-push-orange transition-colors
  disabled:opacity-40 disabled:cursor-not-allowed
`

interface GenrePresetPickerProps {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  /** Show a description chip below the select. Default: true. */
  showDescription?: boolean
  /** Compact: hides description. Overrides showDescription. */
  compact?: boolean
}

export function GenrePresetPicker({
  value,
  onChange,
  disabled = false,
  showDescription = true,
  compact = false,
}: GenrePresetPickerProps) {
  const selected = PRESETS.find(p => p.id === value) ?? PRESETS[0]!

  return (
    <div className="flex flex-col gap-1.5">
      <select
        className={selectClass}
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
      >
        {PRESETS.map(p => (
          <option key={p.id} value={p.id}>
            {p.label}
          </option>
        ))}
      </select>

      {!compact && showDescription && (
        <div className="flex flex-col gap-0.5">
          <p className="text-[9px] text-push-muted leading-relaxed">
            {selected.description}
          </p>
          {selected.targets && (
            <p className="text-[8px] font-mono text-push-orange/70 leading-relaxed">
              {selected.targets}
            </p>
          )}
        </div>
      )}

      {/* Active preset chip */}
      {value !== '' && (
        <div className="flex items-center gap-1.5">
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-[2px]
                       border border-push-orange/60 bg-push-orange/10
                       text-[9px] text-push-orange"
          >
            <span>⊛</span>
            <span>Layer 3: {selected.label}</span>
          </span>
          <button
            onClick={() => onChange('')}
            disabled={disabled}
            className="text-[9px] text-push-muted hover:text-push-text transition-colors
                       disabled:opacity-40 disabled:cursor-not-allowed"
            title="Remove genre preset"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  )
}

/** Returns the list of available preset IDs, useful for dropdowns elsewhere. */
export const GENRE_PRESET_IDS = PRESETS.map(p => p.id)
