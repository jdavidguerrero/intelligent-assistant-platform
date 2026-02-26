import { useCallback, useRef } from 'react'
import clsx from 'clsx'

interface KnobProps {
  value: number           // 0.0 – 1.0 normalized
  label: string
  displayValue?: string
  size?: number           // SVG size in px, default 56
  color?: string          // arc fill color
  onChange?: (value: number) => void
  disabled?: boolean
}

const DEG_TO_RAD = Math.PI / 180
const START_ANGLE = -135 * DEG_TO_RAD  // 7 o'clock
const SWEEP = 270 * DEG_TO_RAD          // 270° sweep

function polarToCartesian(cx: number, cy: number, r: number, angle: number) {
  return {
    x: cx + r * Math.cos(angle),
    y: cy + r * Math.sin(angle),
  }
}

function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
  const start = polarToCartesian(cx, cy, r, startAngle)
  const end = polarToCartesian(cx, cy, r, endAngle)
  const largeArc = endAngle - startAngle > Math.PI ? 1 : 0
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`
}

export function Knob({
  value,
  label,
  displayValue,
  size = 56,
  color = '#FF7700',
  onChange,
  disabled = false,
}: KnobProps) {
  const cx = 50
  const cy = 50
  const r = 36
  const clampedValue = Math.max(0, Math.min(1, value))
  const valueAngle = START_ANGLE + clampedValue * SWEEP

  const trackPath = describeArc(cx, cy, r, START_ANGLE, START_ANGLE + SWEEP)
  const valuePath = clampedValue > 0.001
    ? describeArc(cx, cy, r, START_ANGLE, valueAngle)
    : ''

  // Indicator dot position
  const dot = polarToCartesian(cx, cy, r, valueAngle)

  const dragging = useRef(false)
  const lastY = useRef(0)

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (disabled || !onChange) return
    dragging.current = true
    lastY.current = e.clientY
    e.preventDefault()

    const onMove = (me: MouseEvent) => {
      if (!dragging.current) return
      const dy = lastY.current - me.clientY
      lastY.current = me.clientY
      const delta = dy * 0.005
      const next = Math.max(0, Math.min(1, clampedValue + delta))
      onChange(next)
    }
    const onUp = () => {
      dragging.current = false
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [disabled, onChange, clampedValue])

  return (
    <div className={clsx('flex flex-col items-center gap-1', disabled && 'opacity-40')}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        onMouseDown={handleMouseDown}
        className={clsx('select-none', !disabled && onChange && 'cursor-ns-resize')}
      >
        {/* Background circle */}
        <circle cx={cx} cy={cy} r={42} fill="#1A1A1A" stroke="#2E2E2E" strokeWidth={1.5} />

        {/* Track arc */}
        <path d={trackPath} fill="none" stroke="#333333" strokeWidth={5} strokeLinecap="round" />

        {/* Value arc */}
        {valuePath && (
          <path d={valuePath} fill="none" stroke={color} strokeWidth={5} strokeLinecap="round" />
        )}

        {/* Indicator dot */}
        <circle cx={dot.x} cy={dot.y} r={3.5} fill="#FFFFFF" />
      </svg>
      {displayValue && (
        <span className="push-number text-center leading-none">{displayValue}</span>
      )}
      <span className="push-label">{label}</span>
    </div>
  )
}
