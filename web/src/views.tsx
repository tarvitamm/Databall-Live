import { useState } from 'react'
import { Cards, LowerThird, ScoreBug } from './components/Broadcast'
import { CatchUpModal, RecapPanel, ReplayModal } from './components/Modals'
import { Pitch } from './components/Pitch'
import { Feed, MatchState, PlayerPanel } from './components/Side'
import { clock, type Strings } from './i18n'
import type { Lang, MatchDetail, Packet } from './types'
import type { PitchMaps } from './pitchMaps'
import type { Broadcast } from './useBroadcast'

interface ViewProps {
  match: MatchDetail
  b: Broadcast
  maps: PitchMaps
  s: Strings
  lang: Lang
}

export function Stage({ match, b, maps, s, followed = [] }: ViewProps & { followed?: string[] }) {
  const highlight = b.lowerThird?.data.players?.slice(0, 3) ?? []
  return (
    <div className="pitch-wrap">
      <Pitch clock={b.clock} {...maps} followed={followed} highlight={highlight} tags={b.tags} trails={b.trails} />
      <Cards cards={b.cards} />
      <LowerThird packet={b.lowerThird} match={match} />
      {b.recap && <RecapPanel packet={b.recap} s={s} onClose={b.dismissRecap} />}
      {!b.playing && (
        <button className="start" onClick={b.play}>
          <span aria-hidden>▶</span>
          {b.now.period === 1 && b.now.t < 1 ? s.startHint : s.play}
        </button>
      )}
    </div>
  )
}

function useReplay(match: MatchDetail, maps: PitchMaps, s: Strings) {
  const [packet, setPacket] = useState<Packet | null>(null)
  const modal = packet && <ReplayModal packet={packet} match={match} {...maps} s={s} onClose={() => setPacket(null)} />
  return { open: setPacket, modal }
}

export function FanView({ club, onClub, ...v }: ViewProps & { club: string; onClub: (code: string) => void }) {
  const { match, b, s } = v
  const replay = useReplay(match, v.maps, s)
  const [catchUp, setCatchUp] = useState(false)
  return (
    <div className="stage">
      <Stage {...v} />
      <aside className="side">
        <section className="panel picks">
          <label>
            <span>{s.followClub}</span>
            <select value={club} onChange={(e) => onClub(e.target.value)}>
              <option value="">{s.bothClubs}</option>
              {[match.home, match.away].map((t) => (
                <option key={t.code} value={t.code}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <button className="primary" onClick={() => setCatchUp(true)}>
            {s.catchUp}
          </button>
        </section>
        <MatchState match={match} state={b.state} s={s} />
        <Feed items={b.feed} s={s} onWhy={replay.open} />
      </aside>
      {replay.modal}
      {catchUp && <CatchUpModal match={match} now={b.now} lang={v.lang} s={s} onClose={() => setCatchUp(false)} />}
    </div>
  )
}

function Signals({ signals }: { signals: Record<string, number | number[]> }) {
  return (
    <dl className="signals">
      {Object.entries(signals).map(([k, v]) => (
        <div key={k}>
          <dt>{k.replace(/_/g, ' ')}</dt>
          <dd>{Array.isArray(v) ? `${v[0]} → ${v[1]}` : v}</dd>
        </div>
      ))}
    </dl>
  )
}

function WhyCard({ p, s, onReplay }: { p: Packet; s: Strings; onReplay: () => void }) {
  const why = p.data.why
  const byModel = p.data.source === 'model' || p.data.source === 'cached'
  const analyst = why?.analyst && why.analyst !== 'template' ? why.analyst : s.template
  return (
    <article className="why-card">
      <div className="feed-head">
        <span className="feed-time">{clock(p.period, p.show_at)}</span>
        <span className="feed-title">{p.text.headline}</span>
      </div>
      {p.text.body && <p>{p.text.body}</p>}
      {why && (
        <dl className="why">
          <dt>
            {s.cause} {s.inEnglish}
          </dt>
          <dd>{why.mechanism}</dd>
          <dt>{s.effect}</dt>
          <dd>{why.consequence}</dd>
        </dl>
      )}
      {p.data.signals && <Signals signals={p.data.signals} />}
      <div className="meta">
        <span>
          {s.confidence} {Math.round((p.data.confidence ?? 0) * 100)}%
        </span>
        <span className={`source ${byModel ? 'model' : ''}`}>
          {s.writtenBy} {byModel ? analyst : s.template}
        </span>
        {p.viz && p.data.players?.length ? (
          <button className="link" onClick={onReplay}>
            {s.why}
          </button>
        ) : null}
      </div>
    </article>
  )
}

export function AnalystView(v: ViewProps) {
  const { b, s } = v
  const replay = useReplay(v.match, v.maps, s)
  return (
    <div className="stage">
      <Stage {...v} />
      <aside className="side">
        <MatchState match={v.match} state={b.state} s={s} />
        <section className="panel explained">
          <h3>{s.explained}</h3>
          {b.feed.length === 0 && <p className="muted">{s.noInsights}</p>}
          {b.feed.map((p) => (
            <WhyCard key={p.packet} p={p} s={s} onReplay={() => replay.open(p)} />
          ))}
        </section>
      </aside>
      {replay.modal}
    </div>
  )
}

export function PlayerView({ player, onPlayer, ...v }: ViewProps & { player: string; onPlayer: (pid: string) => void }) {
  const { match, b, s } = v
  const replay = useReplay(match, v.maps, s)
  return (
    <div className="stage">
      <Stage {...v} followed={player ? [player] : []} />
      <aside className="side">
        <section className="panel picks">
          <label>
            <span>{s.followPlayer}</span>
            <select value={player} onChange={(e) => onPlayer(e.target.value)}>
              {[match.home, match.away].map((t) => (
                <optgroup key={t.code} label={t.name}>
                  {match.players
                    .filter((p) => p.team === t.code)
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.shirt} {p.name}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
          </label>
        </section>
        {player && <PlayerPanel match={match} pid={player} now={b.now} s={s} />}
        <Feed items={b.feed} s={s} onWhy={replay.open} />
      </aside>
      {replay.modal}
    </div>
  )
}

export function OverlayView({ match, b }: { match: MatchDetail; b: Broadcast }) {
  return (
    <main className="overlay">
      <ScoreBug match={match} now={b.now} state={b.state} />
      <Cards cards={b.cards} />
      <div className="overlay-tags">
        {b.tags.map((t) => (
          <span key={t.id}>{t.text}</span>
        ))}
      </div>
      <LowerThird packet={b.lowerThird} match={match} />
    </main>
  )
}
