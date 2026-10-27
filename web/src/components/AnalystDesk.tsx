import { useEffect, useState } from 'react'
import { api } from '../api'
import { clock, stateLabel, type Strings } from '../i18n'
import type { PitchMaps } from '../pitchMaps'
import type { Compare, Lang, LiveNumbers, MatchDetail, Packet } from '../types'
import type { Broadcast } from '../useBroadcast'
import { useLive } from '../useLive'
import { Badge } from './Engage'
import { ReplayIcon } from './Icons'
import { EventMaps, LiveText } from './MatchCentre'
import { SceneModal } from './Scene'

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <svg className="spark" viewBox="0 0 120 32" />
  const max = Math.max(0.05, ...values.map(Math.abs))
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 120},${16 - (v / max) * 14}`).join(' ')
  return (
    <svg className="spark" viewBox="0 0 120 32" preserveAspectRatio="none">
      <line x1="0" y1="16" x2="120" y2="16" className="spark-axis" />
      <polyline points={pts} className="spark-line" />
    </svg>
  )
}

function value(v: number | number[]): string {
  return Array.isArray(v) ? `${v[0]} → ${v[1]}` : String(v)
}

function DeskCard({ p, match, maps, s, lang }: { p: Packet; match: MatchDetail; maps: PitchMaps; s: Strings; lang: Lang }) {
  const [open, setOpen] = useState(false)
  const why = p.data.why
  const team = p.data.teams?.[0]
  const tone = team === match.home.code ? 'us' : team === match.away.code ? 'opp' : ''
  const byModel = p.data.source === 'model' || p.data.source === 'cached'
  const writer = why?.analyst && why.analyst !== 'template' ? why.analyst : s.template
  const confidence = Math.round((p.data.confidence ?? 0) * 100)
  return (
    <li className={`desk-card ${tone}`}>
      <div className="k">{clock(p.period, p.show_at)}</div>
      <div className="desk-main">
        <span className="desk-kind">
          {s.kind[p.data.type ?? ''] ?? p.data.type} <Badge p={p} s={s} />
        </span>
        <b>{p.text.headline}</b>
        {p.text.body && <p>{p.text.body}</p>}
        {why && (
          <dl>
            <dt>{s.happened}</dt>
            <dd>{why.claim}</dd>
            <dt>{s.cause}</dt>
            <dd>{why.mechanism}</dd>
            <dt>{s.effect}</dt>
            <dd>{why.consequence}</dd>
          </dl>
        )}
        {why?.lang === 'en' && s.inEnglish && <p className="desk-note">{s.inEnglish}</p>}
        {p.data.signals && (
          <div className="desk-signals">
            {Object.entries(p.data.signals).map(([k, v]) => (
              <span key={k}>
                {k.replace(/_/g, ' ')} <em>{value(v)}</em>
              </span>
            ))}
          </div>
        )}
        <div className="desk-meta">
          <span className="conf">
            <i style={{ width: `${confidence}%` }} />
          </span>
          <span>
            {s.confidence} {confidence}%
          </span>
          <span className={`src ${byModel ? 'model' : ''}`}>
            {s.writtenBy} {byModel ? writer : s.template}
          </span>
          {p.viz && p.viz.kind !== 'none' ? (
            <button className="pill" onClick={() => setOpen(true)}>
              <ReplayIcon />
              {s.scene.explain}
            </button>
          ) : null}
        </div>
        {open && <SceneModal match={match} packet={p} maps={maps} s={s} lang={lang} onClose={() => setOpen(false)} />}
      </div>
    </li>
  )
}

const COMPARE = ['xg', 'shots', 'pressures_per_min', 'possession_pct', 'decoy_runs', 'runs']

function useCompare(match: MatchDetail, now: { period: number; t: number }) {
  const [data, setData] = useState<Compare | null>(null)
  const t = Math.floor(now.t / 30) * 30
  useEffect(() => {
    let live = true
    api.compare(match.id, now.period, t).then((x) => live && setData(x)).catch(() => {})
    return () => {
      live = false
    }
  }, [match.id, now.period, t])
  return data
}

function Delta({ now, usual }: { now: number; usual: number | null }) {
  if (usual === null || usual === 0) return null
  const ratio = now / usual
  if (ratio > 1.15) return <i className="delta up">▲</i>
  if (ratio < 0.85) return <i className="delta down">▼</i>
  return null
}

function Form({ form }: { form: string }) {
  return (
    <span className="form">
      {form.split('').map((r, i) => (
        <i key={i} className={`chip ${r}`}>
          {r}
        </i>
      ))}
    </span>
  )
}

function SeasonTable({ match, b, s }: { match: MatchDetail; b: Broadcast; s: Strings }) {
  const data = useCompare(match, b.now)
  if (!data) return null
  const home = data.teams[match.home.code]
  const away = data.teams[match.away.code]
  if (!home || !away) return null
  return (
    <section className="vs-season">
      <h3 className="desk-title">{s.againstSeason}</h3>
      <table>
        <thead>
          <tr>
            <th />
            <th className="num us">{match.home.name}</th>
            <th className="num">{s.seasonPace}</th>
            <th className="num opp">{match.away.name}</th>
            <th className="num">{s.seasonPace}</th>
          </tr>
        </thead>
        <tbody>
          {COMPARE.map((m) => (
            <tr key={m}>
              <td className="name">{s.cmp[m]}</td>
              <td className="num">
                {home.now[m]} <Delta now={home.now[m]} usual={home.season[m]} />
              </td>
              <td className="num muted">{home.season[m] ?? '-'}</td>
              <td className="num">
                {away.now[m]} <Delta now={away.now[m]} usual={away.season[m]} />
              </td>
              <td className="num muted">{away.season[m] ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="desk-meta">
        <span>{s.form}</span>
        <span className="us-name">{match.home.name}</span>
        <Form form={home.form} />
        <span className="opp-name">{match.away.name}</span>
        <Form form={away.form} />
      </div>
    </section>
  )
}

function LivePanel({ match, data, maps, s, lang }: { match: MatchDetail; data: LiveNumbers; maps: PitchMaps; s: Strings; lang: Lang }) {
  const t = s.live2
  const num = (v: number, d = 0) => (lang === 'en' ? v.toFixed(d) : v.toFixed(d).replace('.', ','))
  const home = data.teams[match.home.code]
  const away = data.teams[match.away.code]
  const name = (pid: string | null | undefined) => (pid ? (maps.names[pid] ?? pid) : '-')
  const rows: [string, string, string][] = [
    [t.passAcc, `${home.pass_accuracy}%`, `${away.pass_accuracy}%`],
    [t.avgDiff, num(home.avg_difficulty, 1), num(away.avg_difficulty, 1)],
    [t.hard, String(home.hard_completed), String(away.hard_completed)],
    [t.fastPass, `${home.fastest_pass_kmh} km/h`, `${away.fastest_pass_kmh} km/h`],
    [t.fastShot, home.fastest_shot_kmh ? `${home.fastest_shot_kmh} km/h` : '-', away.fastest_shot_kmh ? `${away.fastest_shot_kmh} km/h` : '-'],
  ]
  const lead = data.leaders
  return (
    <section className="vs-season live-panel">
      <h3 className="desk-title">{t.title}</h3>
      <table>
        <thead>
          <tr>
            <th />
            <th className="num us">{match.home.name}</th>
            <th className="num opp">{match.away.name}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, h, a]) => (
            <tr key={label}>
              <td className="name">{label}</td>
              <td className="num">{h}</td>
              <td className="num">{a}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="desk-signals">
        <span>
          {t.sprint} <em>{name(lead.sprint.player)} {num(lead.sprint.kmh, 1)} km/h</em>
        </span>
        <span>
          {t.distance} <em>{name(lead.distance.player)} {num(lead.distance.km, 2)} km</em>
        </span>
        {lead.pass && (
          <span>
            {t.hardest} <em>{name(lead.pass.player)} → {name(lead.pass.recipient)}, {num(lead.pass.difficulty, 1)} {t.of10}, {lead.pass.m} m</em>
          </span>
        )}
        {lead.shot && (
          <span>
            {t.fastShot} <em>{name(lead.shot.player)} {lead.shot.kmh} km/h</em>
          </span>
        )}
      </div>
    </section>
  )
}

function Rhythm({ match, data, feed, s }: { match: MatchDetail; data: LiveNumbers; feed: Packet[]; s: Strings }) {
  const W = 600
  const H = 130
  const MID = 64
  const [s1, e1] = data.rhythm.periods['1']
  const [s2, e2] = data.rhythm.periods['2']
  const first = e1 - s1
  const total = first + (e2 - s2)
  const x = (period: number, t: number) => ((period === 1 ? t - s1 : first + (t - s2)) / total) * W
  const m = data.rhythm.momentum
  const scale = 52 / Math.max(0.05, ...m.map((r) => Math.abs(r[2])))
  const pts = m.map((r) => `${x(r[0], r[1]).toFixed(1)},${(MID - r[2] * scale).toFixed(1)}`)
  const area = pts.length > 1 ? `M${pts[0].split(',')[0]},${MID} L${pts.join(' L')} L${pts[pts.length - 1].split(',')[0]},${MID} Z` : ''
  return (
    <section className="vs-season rhythm">
      <h3 className="desk-title">{s.live2.rhythm}</h3>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={s.live2.rhythmNote}>
        <defs>
          <clipPath id="rh-top">
            <rect x="0" y="0" width={W} height={MID} />
          </clipPath>
          <clipPath id="rh-bottom">
            <rect x="0" y={MID} width={W} height={H - MID} />
          </clipPath>
        </defs>
        {data.rhythm.chaos.map(([period, tEnd, chaos]) => (
          <rect key={`${period}-${tEnd}`} className="rh-chaos" x={x(period, tEnd - 300)} y="0" width={Math.max(1, x(period, tEnd) - x(period, tEnd - 300))} height={H - 14} style={{ opacity: Math.max(0, Math.min(0.4, (chaos - 45) / 80)) }} />
        ))}
        <line className="rh-axis" x1="0" x2={W} y1={MID} y2={MID} />
        <line className="rh-half" x1={x(2, s2)} x2={x(2, s2)} y1="0" y2={H - 14} />
        <path className="rh-us" d={area} clipPath="url(#rh-top)" />
        <path className="rh-opp" d={area} clipPath="url(#rh-bottom)" />
        <polyline className="rh-line" points={pts.join(' ')} />
        {feed.map((p) => (
          <line key={p.packet} className="rh-tick" x1={x(p.period, p.show_at)} x2={x(p.period, p.show_at)} y1={H - 12} y2={H - 4} />
        ))}
        {data.rhythm.goals.map(([period, t, team], i) => (
          <g key={i} transform={`translate(${x(period, t)}, ${team === match.home.code ? 10 : H - 26})`}>
            <rect x="-6" y="-6" width="12" height="12" transform="rotate(45)" className={team === match.home.code ? 'rh-goal us' : 'rh-goal opp'} />
          </g>
        ))}
        <text x="2" y={H - 1} className="rh-label">1'</text>
        <text x={x(2, s2) + 3} y={H - 1} className="rh-label">46'</text>
      </svg>
      <p className="desk-note">{s.live2.rhythmNote}</p>
    </section>
  )
}

export function AnalystDesk({ match, b, maps, s, lang }: { match: MatchDetail; b: Broadcast; maps: PitchMaps; s: Strings; lang: Lang }) {
  const st = b.state
  const live = useLive(match, b.now)
  const [home, away] = st?.control ?? [50, 50]
  const share = home + away > 0 ? Math.round((home / (home + away)) * 100) : 50
  return (
    <div className="desk">
      <div className="strip">
        <div>
          <div className="n">
            {st?.xg[match.home.code]?.toFixed(2) ?? '0.00'}
            <small> - {st?.xg[match.away.code]?.toFixed(2) ?? '0.00'}</small>
          </div>
          <div className="l">{s.xg}</div>
        </div>
        <div>
          <div className="n">
            {share}
            <small>%</small>
          </div>
          <div className="l">
            {s.control}, {match.home.name}
          </div>
        </div>
        <div>
          <div className="n">{Math.round(st?.chaos ?? 50)}</div>
          <div className="l">{s.chaos}</div>
        </div>
        <div>
          <Sparkline values={st?.momentum_series ?? []} />
          <div className="l">{stateLabel(st?.label ?? 'balanced', s)}</div>
        </div>
      </div>
      {live && <Rhythm match={match} data={live} feed={b.feed} s={s} />}
      {live && <LivePanel match={match} data={live} maps={maps} s={s} lang={lang} />}
      <div className="centre-grid">
        <EventMaps match={match} now={b.now} maps={maps} s={s} />
        <LiveText match={match} now={b.now} feed={b.feed} s={s} lang={lang} />
      </div>
      <SeasonTable match={match} b={b} s={s} />
      <h3 className="desk-title">{s.explained}</h3>
      {b.feed.length === 0 && <p className="empty">{s.noInsights}</p>}
      <ul className="desk-list">
        {b.feed.map((p) => (
          <DeskCard key={p.packet} p={p} match={match} maps={maps} s={s} lang={lang} />
        ))}
      </ul>
    </div>
  )
}
