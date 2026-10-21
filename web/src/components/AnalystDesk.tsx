import { useEffect, useState } from 'react'
import { api } from '../api'
import { clock, stateLabel, type Strings } from '../i18n'
import type { PitchMaps } from '../pitchMaps'
import type { Compare, Lang, MatchDetail, Packet } from '../types'
import type { Broadcast } from '../useBroadcast'
import { Badge } from './Engage'
import { ReplayIcon } from './Icons'
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
          {p.viz ? (
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

export function AnalystDesk({ match, b, maps, s, lang }: { match: MatchDetail; b: Broadcast; maps: PitchMaps; s: Strings; lang: Lang }) {
  const st = b.state
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
