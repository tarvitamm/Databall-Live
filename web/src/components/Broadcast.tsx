import { clock } from '../i18n'
import type { MatchDetail, Packet, StateMsg } from '../types'

export function ScoreBug({ match, now, state }: { match: MatchDetail; now: { period: number; t: number }; state: StateMsg | null }) {
  const score = state?.score ?? { [match.home.code]: 0, [match.away.code]: 0 }
  return (
    <div className="scorebug">
      <span className="sb-team" style={{ borderColor: match.home.colours[0] }}>{match.home.code}</span>
      <span className="sb-score">
        {score[match.home.code] ?? 0}
        <i>-</i>
        {score[match.away.code] ?? 0}
      </span>
      <span className="sb-team" style={{ borderColor: match.away.colours[0] }}>{match.away.code}</span>
      <span className="sb-clock">{clock(now.period, now.t)}</span>
    </div>
  )
}

export function LowerThird({ packet, match }: { packet: Packet | null; match: MatchDetail }) {
  if (!packet) return null
  const team = packet.data.teams?.[0]
  const colour = team === match.home.code ? match.home.colours[0] : team === match.away.code ? match.away.colours[0] : '#3ddc97'
  return (
    <div className="lower-third" key={packet.packet}>
      <div className="lt-bar" style={{ background: colour }} />
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
