import clsx from 'clsx'

interface SpectrumBarProps {
  value: number       // measured dBFS
  target: number      // genre target dBFS
  label: string       // band short name e.g. 'SUB'
  rangeLabel?: string // e.g. '20-60Hz'
  height?: number
  className?: string
}

function deviationColor(diff: number): string {
  const abs = Math.abs(diff)
  if (abs <= 2) return '#3D8D40'   // within ±2dB — green
  if (abs <= 4) return '#B5A020'   // ±2-4dB — yellow
  return '#B02020'                  // >±4dB — red
}

export function SpectrumBar({
  value,
  target,
  label,
  rangeLabel,
  height = 120,
  className,
}: SpectrumBarProps) {
  // Map dB range -40 to 0 into 0-1 for display
  const DB_MIN = -40
  const DB_MAX = 0
  const normalize = (db: number) => (db - DB_MIN) / (DB_MAX - DB_MIN)

  const valuePct = Math.max(0, Math.min(1, normalize(value)))
  const targetPct = Math.max(0, Math.min(1, normalize(target)))

  const color = deviationColor(value - target)
  const barH = valuePct * (height - 16)    // 16px reserved for label
  const targetY = (1 - targetPct) * (height - 16)

  return (
    <div
      className={clsx('flex flex-col items-center', className)}
      style={{ width: 32 }}
      title={`${label}: ${value.toFixed(1)} dBFS (target: ${target.toFixed(1)} dBFS)`}
    >
      <div className="relative" style={{ width: 20, height: height - 16 }}>
        {/* Track background */}
        <div
          className="absolute bottom-0 left-0 right-0 rounded-sm"
          style={{ backgroundColor: '#2A2A2A', height: '100%' }}
        />
        {/* Value bar */}
        <div
          className="absolute bottom-0 left-0 right-0 rounded-sm transition-all duration-300"
          style={{ backgroundColor: color, height: `${barH}px` }}
        />
        {/* Target line */}
        <div
          className="absolute left-0 right-0"
          style={{
            top: `${targetY}px`,
            height: 1.5,
            backgroundColor: 'rgba(255,255,255,0.5)',
            borderTop: '1.5px dashed rgba(255,255,255,0.5)',
          }}
        />
      </div>
      <span className="push-label mt-1 text-center leading-tight">{label}</span>
      {rangeLabel && (
        <span
          className="text-center leading-tight"
          style={{ fontSize: 7, color: '#444', letterSpacing: '0.04em' }}
        >
          {rangeLabel}
        </span>
      )}
    </div>
  )
}
