import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Strings } from '../i18n'
import type { PitchMaps } from '../pitchMaps'
import type { FantasyRow, MatchDetail } from '../types'

const COUNTED = new Set(['offball', 'saves', 'conceded'])

function loadSquad(): string[] {
  try {
    return JSON.parse(localStorage.getItem('databall.fantasy') ?? '[]') as string[]
  } catch {
    return []
  }
}

function useFantasy(match: MatchDetail, now: { period: number; t: number }) {
  const [data, setData] = useState<{ rows: FantasyRow[]; before: Record<string, number> } | null>(null)
  const t = Math.floor(now.t / 10) * 10
  useEffect(() => {
    let live = true
    api
      .fantasy(match.id, now.period, t)
      .then((rows) => live && setData((prev) => ({ rows, before: Object.fromEntries((prev?.rows ?? rows).map((r, i) => [r.id, i])) })))
      .catch(() => {})
    return () => {
      live = false
    }
  }, [match.id, now.period, t])
  return data
}

export function FantasyPanel({ match, now, maps, s }: { match: MatchDetail; now: { period: number; t: number }; maps: PitchMaps; s: Strings }) {
  const data = useFantasy(match, now)
  const [squad, setSquad] = useState<string[]>(loadSquad)
  const [open, setOpen] = useState<string | null>(null)
  const t = s.fantasy
  useEffect(() => {
    try {
      localStorage.setItem('databall.fantasy', JSON.stringify(squad))
    } catch {
      return
    }
  }, [squad])
  if (!data) return null
  const yours = data.rows.filter((r) => squad.includes(r.id))
  const toggle = (id: string) => setSquad((all) => (all.includes(id) ? all.filter((x) => x !== id) : [...all, id]))
  return (
    <section className="fantasy">
      <div className="fantasy-yours">
        <span>{t.yours}</span>
        <b>
          {yours.reduce((sum, r) => sum + r.points, 0)} {s.pts}
        </b>
        <small>{yours.length ? yours.map((r) => `${maps.names[r.id] ?? r.id} ${r.points}`).join(' · ') : t.pick}</small>
      </div>
      <ol className="fantasy-list">
        {data.rows.map((r, i) => {
          const moved = (data.before[r.id] ?? i) - i
          return (
            <li key={r.id} className={`${squad.includes(r.id) ? 'mine' : ''} ${r.team === match.home.code ? 'us' : 'opp'}`}>
              <div className="fantasy-row">
                <span className="rank">
                  {i + 1}
                  {moved !== 0 && <i className={moved > 0 ? 'up' : 'down'}>{moved > 0 ? '▲' : '▼'}</i>}
                </span>
                <button className="who" onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
                  <b>{maps.names[r.id] ?? r.id}</b>
                  <small>
                    {r.role} · {r.team === match.home.code ? match.home.name : match.away.name}
                  </small>
                </button>
                <em>{r.points}</em>
                <button className={`star ${squad.includes(r.id) ? 'on' : ''}`} aria-pressed={squad.includes(r.id)} aria-label={t.star} onClick={() => toggle(r.id)}>
                  {squad.includes(r.id) ? '★' : '☆'}
                </button>
              </div>
              {open === r.id && (
                <ul className="fantasy-items">
                  {r.items.map(([key, n, pts]) => (
                    <li key={key}>
                      <span>
                        {t.items[key] ?? key}
                        {key === 'defence' ? ` · ${n}/${r.role === 'MID' || r.role === 'FWD' ? 12 : 10}` : COUNTED.has(key) || n > 1 ? ` · ${n}` : ''}
                      </span>
                      <b>{pts > 0 ? `+${pts}` : pts}</b>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          )
        })}
      </ol>
      <p className="muted small">{t.how}</p>
    </section>
  )
}
