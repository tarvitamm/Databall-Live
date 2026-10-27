import { useEffect, useState } from 'react'
import { api } from '../api'
import { clock, fill, type Strings } from '../i18n'
import type { PitchMaps } from '../pitchMaps'
import type { Lang, LiveLine, MapKind, MatchDetail, Packet, TeamMaps } from '../types'

const KINDS: MapKind[] = ['shots', 'passes', 'dribbles', 'decoys', 'pressing', 'attacking', 'duels', 'defending']
const GRID = [7, 5]

type Now = { period: number; t: number }

function useMaps(match: MatchDetail, now: Now): Record<string, TeamMaps> | null {
  const [data, setData] = useState<Record<string, TeamMaps> | null>(null)
  const t = Math.floor(now.t / 20) * 20
  useEffect(() => {
    let live = true
    api.maps(match.id, now.period, t).then((x) => live && setData(x)).catch(() => {})
    return () => {
      live = false
    }
  }, [match.id, now.period, t])
  return data
}

function useLines(match: MatchDetail, now: Now, lang: Lang): LiveLine[] {
  const [data, setData] = useState<LiveLine[]>([])
  const t = Math.floor(now.t / 5) * 5
  useEffect(() => {
    let live = true
    api.commentary(match.id, now.period, t, lang).then((x) => live && setData(x)).catch(() => {})
    return () => {
      live = false
    }
  }, [match.id, now.period, t, lang])
  return data
}

const pct = (a: number, b: number) => (b ? Math.round((100 * a) / b) : 0)
const Y = (y: number) => 68 - y

function PitchLines() {
  return (
    <g className="map-lines">
      <rect x={0} y={0} width={105} height={68} />
      <line x1={52.5} y1={0} x2={52.5} y2={68} />
      <circle cx={52.5} cy={34} r={9.15} />
      <rect x={0} y={13.84} width={16.5} height={40.32} />
      <rect x={88.5} y={13.84} width={16.5} height={40.32} />
      <rect x={0} y={24.84} width={5.5} height={18.32} />
      <rect x={99.5} y={24.84} width={5.5} height={18.32} />
    </g>
  )
}

function summary(kind: MapKind, m: TeamMaps, s: Strings, maps: PitchMaps, lang: Lang): string {
  const t = s.centre.sum
  if (kind === 'shots') {
    const xg = m.shots.reduce((a, x) => a + x[2], 0)
    const v = lang === 'en' ? xg.toFixed(2) : xg.toFixed(2).replace('.', ',')
    return fill(t.shots, { n: m.shots.length, xg: v, g: m.shots.filter((x) => x[3] === 'goal').length })
  }
  if (kind === 'passes') return fill(t.passes, { n: m.passes.length, pct: pct(m.passes.filter((x) => x[4]).length, m.passes.length) })
  if (kind === 'dribbles') {
    const fwd = m.dribbles.reduce((a, x) => a + (x[2] - x[0]), 0) / Math.max(m.dribbles.length, 1)
    return fill(t.dribbles, { n: m.dribbles.length, m: Math.round(fwd) })
  }
  if (kind === 'decoys') {
    const count: Record<string, number> = {}
    for (const x of m.decoys) count[x[4]] = (count[x[4]] ?? 0) + 1
    const [top, k] = Object.entries(count).sort((a, b) => b[1] - a[1])[0] ?? ['', 0]
    return fill(t.decoys, { n: m.decoys.length, name: maps.names[top] ?? '-', k })
  }
  if (kind === 'pressing') return fill(t.pressing, { n: m.pressing.length, pct: pct(m.pressing.filter((x) => x[0] > 52.5).length, m.pressing.length) })
  if (kind === 'attacking') {
    const n = m.attacking.length
    const lane = (f: (y: number) => boolean) => pct(m.attacking.filter((x) => f(x[3])).length, n)
    return fill(t.attacking, { n, l: lane((y) => y > 45.3), c: lane((y) => y >= 22.7 && y <= 45.3), r: lane((y) => y < 22.7) })
  }
  if (kind === 'duels') return fill(t.duels, { won: m.duels.filter((x) => x[2]).length, n: m.duels.length })
  const of = (k: string) => m.defending.filter((x) => x[2] === k).length
  return fill(t.defending, { i: of('interception'), c: of('clearance'), r: of('ball_recovery') })
}

function Marks({ kind, m, side }: { kind: MapKind; m: TeamMaps; side: string }) {
  if (kind === 'shots')
    return m.shots.map(([x, y, xg, outcome], i) => <circle key={i} className={`shot ${outcome} ${side}`} cx={x} cy={Y(y)} r={0.9 + xg * 4} />)
  if (kind === 'passes' || kind === 'attacking')
    return m[kind].map(([x1, y1, x2, y2, done], i) => (
      <g key={i} className={done ? `pass ${side}` : 'pass failed'}>
        <line x1={x1} y1={Y(y1)} x2={x2} y2={Y(y2)} />
        <circle cx={x2} cy={Y(y2)} r={0.45} />
      </g>
    ))
  if (kind === 'dribbles' || kind === 'decoys')
    return m[kind].map(([x1, y1, x2, y2], i) => (
      <g key={i} className={`${kind === 'decoys' ? 'run' : 'carry'} ${side}`}>
        <line x1={x1} y1={Y(y1)} x2={x2} y2={Y(y2)} />
        <circle cx={x2} cy={Y(y2)} r={kind === 'decoys' ? 0.9 : 0.5} />
      </g>
    ))
  if (kind === 'pressing') {
    const [cols, rows] = GRID
    const cells = new Array(cols * rows).fill(0)
    for (const [x, y] of m.pressing) cells[Math.min(cols - 1, Math.floor((x / 105) * cols)) + cols * Math.min(rows - 1, Math.floor((Y(y) / 68) * rows))]++
    const top = Math.max(...cells, 1)
    return cells.map((n, i) => (
      <rect key={i} className={`heat ${side}`} x={(i % cols) * (105 / cols)} y={Math.floor(i / cols) * (68 / rows)} width={105 / cols} height={68 / rows} opacity={(0.75 * n) / top} />
    ))
  }
  if (kind === 'duels') return m.duels.map(([x, y, won], i) => <circle key={i} className={won ? 'duel won' : 'duel lost'} cx={x} cy={Y(y)} r={0.9} />)
  return m.defending.map(([x, y, k], i) => <circle key={i} className={`def ${k} ${side}`} cx={x} cy={Y(y)} r={0.9} />)
}

const LEGEND: Partial<Record<MapKind, string[]>> = {
  shots: ['goal', 'saved', 'off_target', 'blocked'],
  passes: ['complete', 'failed'],
  attacking: ['complete', 'failed'],
  duels: ['won', 'lost'],
  defending: ['interception', 'clearance', 'ball_recovery'],
}

export function EventMaps({ match, now, maps, s, lang }: { match: MatchDetail; now: Now; maps: PitchMaps; s: Strings; lang: Lang }) {
  const data = useMaps(match, now)
  const [team, setTeam] = useState(match.home.code)
  const [kind, setKind] = useState<MapKind>('shots')
  const m = data?.[team]
  const side = team === match.home.code ? 'us' : 'opp'
  return (
    <section className="event-maps">
      <h5 className="app-section">{s.centre.maps}</h5>
      <div className="app-chips">
        {[match.home, match.away].map((x) => (
          <button key={x.code} className={team === x.code ? 'on' : ''} onClick={() => setTeam(x.code)}>
            {x.name}
          </button>
        ))}
      </div>
      <div className="app-chips map-kinds">
        {KINDS.map((k) => (
          <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>
            {s.centre.kinds[k]}
          </button>
        ))}
      </div>
      <svg className="map" viewBox="-2 -2 109 72" role="img" aria-label={`${s.centre.kinds[kind]}, ${team}`}>
        <PitchLines />
        {m && <Marks kind={kind} m={m} side={side} />}
      </svg>
      <div className="map-foot">
        <span className="map-dir">
          {s.centre.attacking} →
        </span>
        {(LEGEND[kind] ?? []).map((k) => (
          <span key={k} className={`map-key ${k} ${side}`}>
            <i />
            {s.centre.legend[k]}
          </span>
        ))}
      </div>
      <p className="map-sum">{m ? summary(kind, m, s, maps, lang) : s.centre.none}</p>
    </section>
  )
}

export function LiveText({ match, now, feed, s, lang }: { match: MatchDetail; now: Now; feed: Packet[]; s: Strings; lang: Lang }) {
  const lines = useLines(match, now, lang)
  const items = [
    ...lines.map((l) => ({ key: `${l.period}${l.t}${l.kind}`, period: l.period, t: l.t, kind: l.kind, team: l.team, text: l.text, body: '' })),
    ...feed.map((p) => ({ key: p.packet, period: p.period, t: p.show_at, kind: 'insight', team: p.data.teams?.[0] ?? null, text: p.text.headline, body: p.text.body ?? '' })),
  ]
    .sort((a, b) => b.period - a.period || b.t - a.t)
    .slice(0, 80)
  return (
    <section className="live-text">
      <h5 className="app-section">{s.centre.liveText}</h5>
      {items.length === 0 && <p className="app-empty">{s.centre.none}</p>}
      <ol>
        {items.map((x) => (
          <li key={x.key} className={`${x.kind} ${x.team === match.home.code ? 'us' : x.team ? 'opp' : ''}`}>
            <span className="time">{clock(x.period, x.t)}</span>
            <div>
              {x.kind === 'insight' && <small>{s.centre.insight}</small>}
              <p>{x.text}</p>
              {x.body && <p className="body">{x.body}</p>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
