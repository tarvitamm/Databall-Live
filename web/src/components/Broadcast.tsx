import { clock } from '../i18n'
import type { MatchDetail, Packet, StateMsg } from '../types'

export function ScoreBug({ match, now, state }: { match: MatchDetail; now: { period: number; t: number }; state: StateMsg | null }) {
  const score = state?.score ?? {}
  return (
    <div className="scorebug">
      <span className="sb-team us">{match.home.code}</span>
      <span className="sb-score">
        {score[match.home.code] ?? 0}
        <i>-</i>
        {score[match.away.code] ?? 0}
      </span>
      <span className="sb-team opp">{match.away.code}</span>
      <span className="sb-clock">{clock(now.period, now.t)}</span>
    </div>
  )
}

export function LowerThird({ packet, match }: { packet: Packet | null; match: MatchDetail }) {
  if (!packet) return null
  const team = packet.data.teams?.[0]
  const tone = team === match.home.code ? 'us' : team === match.away.code ? 'opp' : ''
  return (
    <div className={`lower-third ${tone}`} key={packet.packet}>
      <div className="lt-bar" />
      <div className="lt-text">
        <div className="lt-headline">{packet.text.headline}</div>
        {packet.text.body && <div className="lt-body">{packet.text.body}</div>}
      </div>
    </div>
  )
}

export function Cards({ cards }: { cards: Packet[] }) {
  return (
    <div className="cards">
      {cards.map((c) => (
        <div key={c.packet} className={`card card-${c.slot}`}>
          {c.text.headline}
        </div>
      ))}
    </div>
  )
}

export function RecapPanel({ packet, onClose, close }: { packet: Packet; onClose: () => void; close: string }) {
  return (
    <div className="recap">
      <div className="eyebrow">{packet.text.headline}</div>
      <p>{packet.text.body}</p>
      <button className="pill" onClick={onClose}>
        {close}
      </button>
    </div>
  )
}
