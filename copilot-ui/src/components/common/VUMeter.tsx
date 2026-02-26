import { useMemo, useRef, useEffect } from 'react'
import clsx from 'clsx'

interface VUMeterProps {
  level: number     // 0.0 – 1.0
  peak?: number     // 0.0 – 1.0 for peak hold
  width?: number
  height?: number
  segments?: number
  label?: string
  className?: string
}

const SEGMENT_COLORS = (idx: number, total: number) => {
  const pct = idx / total
  if (pct >= 0.85) return '#B02020'   // red — top 15%
  if (pct >= 0.65) return '#B5A020'   // yellow
  return '#3D8D40'                     // green
}

export function VUMeter({
  level,
  peak,
  width = 14,
  height = 80,
  segments = 20,
  label,
  className,
}: VUMeterProps) {
  const clamped = Math.max(0, Math.min(1, level))
  const activeSeg = Math.round(clamped * segments)
  const peakSeg = peak != null ? Math.round(Math.max(0, Math.min(1, peak)) * segments) : -1

  const segH = Math.floor((height - (segments - 1)) / segments)
  const gap = 1

  const rects = useMemo(() => Array.from({ length: segments }, (_, i) => ({
    idx: i,
    active: i < activeSeg,
    isPeak: i === peakSeg,
    color: SEGMENT_COLORS(i, segments),
    y: height - (i + 1) * segH - i * gap,
  })), [segments, activeSeg, peakSeg, segH, gap, height])

  const peakTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (peakTimerRef.current) clearTimeout(peakTimerRef.current)
    peakTimerRef.current = setTimeout(() => { /* peak decay handled in parent */ }, 1500)
    return () => { if (peakTimerRef.current) clearTimeout(peakTimerRef.current) }
  }, [peak])

  return (
    <div className={clsx('flex flex-col items-center gap-1', className)}>
      <svg width={width} height={height}>
        {rects.map(({ idx, active, isPeak, color, y }) => (
          <rect
            key={idx}
            x={0}
            y={y}
            width={width}
            height={segH}
            fill={isPeak ? '#FFFFFF' : active ? color : '#2A2A2A'}
            rx={1}
          />
        ))}
      </svg>
      {label && <span className="push-label">{label}</span>}
    </div>
  )
}
