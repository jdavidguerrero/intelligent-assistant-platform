import clsx from 'clsx'

interface FaderProps {
  value: number     // 0.0 – 1.0 (maps from dB)
  label?: string
  height?: number
  color?: string
  className?: string
}

export function Fader({
  value,
  label,
  height = 60,
  color = '#FF7700',
  className,
}: FaderProps) {
  const clamped = Math.max(0, Math.min(1, value))
  const thumbY = (1 - clamped) * (height - 8)

  return (
    <div className={clsx('flex flex-col items-center gap-1', className)}>
      <div className="relative flex justify-center" style={{ height, width: 12 }}>
        {/* Track */}
        <div
          className="absolute rounded-full"
          style={{
            width: 2,
            top: 4,
            bottom: 4,
            backgroundColor: '#2E2E2E',
            left: '50%',
            transform: 'translateX(-50%)',
          }}
        />
        {/* Fill below thumb */}
        <div
          className="absolute rounded-full"
          style={{
            width: 2,
            top: thumbY + 8,
            bottom: 4,
            backgroundColor: color,
            left: '50%',
            transform: 'translateX(-50%)',
          }}
        />
        {/* Thumb */}
        <div
          className="absolute rounded-sm"
          style={{
            width: 12,
            height: 4,
            backgroundColor: '#D4D4D4',
            top: thumbY + 2,
            left: 0,
          }}
        />
      </div>
      {label && <span className="push-label">{label}</span>}
    </div>
  )
}
