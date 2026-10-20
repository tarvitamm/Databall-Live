import { useEffect, useState } from 'react'
import { api } from '../api'
import { clock, stateLabel, type Strings } from '../i18n'
import type { MatchDetail, Packet, PlayerStats, StateMsg } from '../types'

export function Feed({ items, s, onWhy }: { items: Packet[]; s: Strings; onWhy: (p: Packet) => void }) {
  return (
    <section className="panel feed">
      <h3>{s.feed}</h3>
      {items.length === 0 && <p className="muted">{s.noInsights}</p>}
      <ul>
        {items.map((p) => (
          <li key={p.packet}>
            <div className="feed-head">
              <span className="feed-time">{clock(p.period, p.show_at)}</span>
              <span className="feed-title">{p.text.headline}</span>
            </div>
            {p.text.body && <p>{p.text.body}</p>}
            {p.viz && p.data.players?.length ? (
              <button className="link" onClick={() => onWhy(p)}>
                {s.why}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  )
}

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

export function MatchState({ match, state, s }: { match: MatchDetail; state: StateMsg | null; s: Strings }) {
  const [home, away] = state?.control ?? [50, 50]
  const share = home + away > 0 ? (home / (home + away)) * 100 : 50
  const chaos = state?.chaos ?? 50
  return (
    <section className="panel state">
      <div className="state-row">
        <span>{s.control}</span>
        <div className="split-bar">
          <div style={{ width: `${share}%`, background: match.home.colours[0] }} />
          <div style={{ width: `${100 - share}%`, background: match.away.colours[0] }} />
        </div>
      </div>
      <div className="state-row">
        <span>{s.chaos}</span>
        <div className="gauge">
          <div style={{ width: `${chaos}%` }} className={chaos >= 65 ? 'hot' : ''} />
        </div>
      </div>
      <div className="state-row">
        <span>{s.momentum}</span>
        <Sparkline values={state?.momentum_series ?? []} />
      </div>
      <div className="state-foot">
        <span>
          {s.xg} {state?.xg[match.home.code]?.toFixed(2) ?? '0.00'} - {state?.xg[match.away.code]?.toFixed(2) ?? '0.00'}
        </span>
        <span className="muted">{stateLabel(state?.label ?? 'balanced', s)}</span>
      </div>
    </section>
  )
}

export function PlayerPanel({ match, pid, now, s }: { match: MatchDetail; pid: string; now: { period: number; t: number }; s: Strings }) {
  const [stats, setStats] = useState<PlayerStats | null>(null)
  const t = Math.floor(now.t / 10) * 10
  useEffect(() => {
    let live = true
    api.player(match.id, pid, now.period, t).then((x) => live && setStats(x)).catch(() => {})
    return () => {
      live = false
    }
  }, [match.id, pid, now.period, t])
  const player = match.players.find((p) => p.id === pid)
  if (!player) return null
  const runs = stats ? Object.values(stats.runs).reduce((a, b) => a + b, 0) : 0
  return (
    <section className="panel player">
      <div className="player-head">
        <span className="shirt">{player.shirt}</span>
        <div>
          <div className="player-name">{player.name}</div>
          <div className="muted">{player.position}</div>
        </div>
      </div>
      {stats && (
        <>
          <h4>{s.offBall}</h4>
          <dl>
            <dt>{s.runs}</dt>
            <dd>{runs}</dd>
            <dt>{s.decoys}</dt>
            <dd>{stats.decoy_runs}</dd>
            <dt>{s.dragged}</dt>
            <dd>{stats.defenders_dragged_m} m</dd>
            <dt>{s.pressures}</dt>
            <dd>{stats.pressures}</dd>
            <dt>{s.recoveries}</dt>
            <dd>{stats.recovery_runs}</dd>
          </dl>
          <h4>{s.onBall}</h4>
          <dl>
            <dt>{s.passes}</dt>
            <dd>
              {stats.passes_complete}/{stats.passes}
            </dd>
            <dt>{s.distance}</dt>
            <dd>{stats.distance_km} km</dd>
            <dt>{s.sprints}</dt>
            <dd>{stats.sprints}</dd>
            <dt>{s.topSpeed}</dt>
            <dd>{stats.top_speed_kmh} km/h</dd>
          </dl>
        </>
      )}
    </section>
  )
}
