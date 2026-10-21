import { useState } from 'react'
import { clock } from '../i18n'
import type { MatchDetail } from '../types'

export interface Mark {
  id: string
  period: number
  t: number
  tone: string
}

interface Props {
  match: MatchDetail
  now: { period: number; t: number }
  marks: Mark[]
  onSeek: (period: number, t: number) => void
}

export function Timeline({ match, now, marks, onSeek }: Props) {
  const [p1Start, p1End] = match.periods['1']
  const [p2Start, p2End] = match.periods['2']
  const first = p1End - p1Start
  const total = first + (p2End - p2Start)
  const toAbs = (period: number, t: number) => (period === 1 ? t - p1Start : first + (t - p2Start))
  const [drag, setDrag] = useState<number | null>(null)
  const value = drag ?? toAbs(now.period, now.t)
  const commit = () => {
    if (drag === null) return
    if (drag < first) onSeek(1, p1Start + drag)
    else onSeek(2, p2Start + (drag - first))
    setDrag(null)
  }
  const label = value < first ? clock(1, p1Start + value) : clock(2, p2Start + (value - first))
  return (
    <div className="timeline">
      <div className="track">
        <div className="played" style={{ width: `${(value / total) * 100}%` }} />
        <i className="half" style={{ left: `${(first / total) * 100}%` }} />
        {marks.map((m) => (
          <i key={m.id} className={`mark ${m.tone}`} style={{ left: `${(toAbs(m.period, m.t) / total) * 100}%` }} />
        ))}
        <input
          type="range"
          min={0}
          max={Math.round(total)}
          step={10}
          value={Math.round(value)}
          onChange={(e) => setDrag(Number(e.target.value))}
          onMouseUp={commit}
          onTouchEnd={commit}
          onKeyUp={commit}
          aria-label="Match time"
        />
      </div>
      <span>{label}</span>
    </div>
  )
}
