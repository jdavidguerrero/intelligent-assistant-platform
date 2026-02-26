import clsx from 'clsx'

type SeverityBadgeProps = { variant: 'severity'; value: number; label?: string }
type StatusBadgeProps = { variant: 'status'; value: string; label?: string }
type BadgeProps = SeverityBadgeProps | StatusBadgeProps

function severityColor(v: number): string {
  if (v >= 7) return '#B02020'
  if (v >= 4) return '#B5A020'
  return '#3D8D40'
}

export function Badge(props: BadgeProps) {
  if (props.variant === 'severity') {
    const { value, label } = props
    const color = severityColor(value)
    return (
      <span
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-medium"
        style={{ backgroundColor: color + '22', color, border: `1px solid ${color}44` }}
        title={label}
      >
        {value.toFixed(0)}
      </span>
    )
  }

  // Status badge
  const { value } = props
  const colorMap: Record<string, string> = {
    connected:    '#3D8D40',
    disconnected: '#666666',
    connecting:   '#B5A020',
    error:        '#B02020',
    rag:          '#3D7EB1',
    tool:         '#FF7700',
    degraded:     '#B5A020',
  }
  const color = colorMap[value] ?? '#666666'

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded',
        'text-[9px] uppercase tracking-wider font-medium'
      )}
      style={{ backgroundColor: color + '22', color, border: `1px solid ${color}44` }}
    >
      <span
        className="inline-block rounded-full"
        style={{ width: 5, height: 5, backgroundColor: color }}
      />
      {value}
    </span>
  )
}
