import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { MatchClock } from '../clock'
import { stateLabel, type Strings } from '../i18n'
import type { CatchUp, FrameMsg, MatchDetail, Packet } from '../types'
import { Pitch, type Trail } from './Pitch'

const COLOURS = ['#ffd166', '#ff6b6b', '#3ddc97']

interface Common {
  match: MatchDetail
  teamOf: Record<string, number>
  shirts: Record<string, number>
  names: Record<string, string>
  colours: [[string, string], [string, string]]
  s: Strings
  onClose: () => void
}

export function ReplayModal({ packet, ...c }: Common & { packet: Packet }) {
  const clock = useMemo(() => new MatchClock(), [])
  const [frames, setFrames] = useState<FrameMsg[]>([])
  const players = useMemo(() => (packet.data.players ?? []).slice(0, 3), [packet])

  useEffect(() => {
    if (!packet.viz) return
    const [start, end] = packet.viz.window
    api.replay(c.match.id, packet.period, start - 2, Math.min(end, packet.show_at) + 2).then((r) => setFrames(r.frames))
  }, [packet, c.match.id])

  useEffect(() => {
    if (!frames.length) return
    let k = 0
    const timer = setInterval(() => {
      clock.push(frames[k])
      k = (k + 1) % frames.length
    }, 200)
    return () => clearInterval(timer)
  }, [frames, clock])

  const trails: Trail[] = players.map((pid, i) => ({
    player: pid,
    points: frames.map((f) => f.players[pid]).filter(Boolean),
    colour: COLOURS[i],
  }))

  return (
    <div className="modal" onClick={c.onClose}>
      <div className="modal-card wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <div className="eyebrow">{c.s.replay}</div>
            <h2>{packet.text.headline}</h2>
            {packet.text.body && <p>{packet.text.body}</p>}
          </div>
          <button className="ghost" onClick={c.onClose}>
            {c.s.close}
          </button>
        </div>
        <Pitch clock={clock} teamOf={c.teamOf} shirts={c.shirts} names={c.names} colours={c.colours} followed={[]} highlight={players} tags={[]} trails={trails} />
        <div className="legend">
          {players.map((pid, i) => (
            <span key={pid}>
              <i style={{ background: COLOURS[i] }} />
              {c.names[pid]}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

export function CatchUpModal({ match, now, lang, s, onClose }: { match: MatchDetail; now: { period: number; t: number }; lang: string; s: Strings; onClose: () => void }) {
  const [data, setData] = useState<CatchUp | null>(null)
  useEffect(() => {
    api.catchUp(match.id, now.period, now.t, lang).then(setData)
  }, [match.id, now.period, now.t, lang])
  return (
    <div className="modal" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{s.catchUp}</h2>
          <button className="ghost" onClick={onClose}>
            {s.close}
          </button>
        </div>
        {data && (
          <>
            <div className="catchup-score">
              <span>{match.home.name}</span>
              <strong>
                {data.score[match.home.code]} - {data.score[match.away.code]}
              </strong>
              <span>{match.away.name}</span>
            </div>
            <p className="muted center">
              {s.xg} {data.xg[match.home.code]?.toFixed(2)} - {data.xg[match.away.code]?.toFixed(2)} · {stateLabel(data.state.label, s)}
            </p>
            <h4>{s.keyMoments}</h4>
            <ol className="moments">
              {data.moments.map((m, i) => (
                <li key={i}>
                  <strong>{m.headline}</strong>
                  {m.body && <p>{m.body}</p>}
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </div>
  )
}

export function RecapPanel({ packet, s, onClose }: { packet: Packet; s: Strings; onClose: () => void }) {
  return (
    <div className="recap">
      <div className="eyebrow">{packet.text.headline}</div>
      <p>{packet.text.body}</p>
      <button className="ghost" onClick={onClose}>
        {s.close}
      </button>
    </div>
  )
}
