import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { Cards, LowerThird, ScoreBug } from './components/Broadcast'
import { Controls } from './components/Controls'
import { CatchUpModal, RecapPanel, ReplayModal } from './components/Modals'
import { Pitch } from './components/Pitch'
import { Feed, MatchState, PlayerPanel } from './components/Side'
import { Timeline } from './components/Timeline'
import { strings, type Strings } from './i18n'
import type { MatchDetail, MatchSummary, Packet, Profile } from './types'
import { useMatchStream } from './useMatchStream'

function useMatch(id: string) {
  const [match, setMatch] = useState<MatchDetail | null>(null)
  useEffect(() => {
    api.match(id).then(setMatch)
  }, [id])
  return match
}

function usePitchMaps(match: MatchDetail | null) {
  return useMemo(() => {
    const teamOf: Record<string, number> = {}
    const shirts: Record<string, number> = {}
    const names: Record<string, string> = {}
    for (const p of match?.players ?? []) {
      teamOf[p.id] = p.team === match?.home.code ? 0 : 1
      shirts[p.id] = p.shirt
      names[p.id] = p.name.split(' ').slice(-1)[0]
    }
    const colours: [[string, string], [string, string]] = [
      match?.home.colours ?? ['#0b3d91', '#ffffff'],
      match?.away.colours ?? ['#b22222', '#ffffff'],
    ]
    return { teamOf, shirts, names, colours }
  }, [match])
}

export function MatchPicker({ s, onPick }: { s: Strings; onPick: (id: string) => void }) {
  const [matches, setMatches] = useState<MatchSummary[]>([])
  useEffect(() => {
    api.matches().then(setMatches)
  }, [])
  return (
    <main className="picker">
      <header className="brand">
        <h1>Blindside</h1>
        <p>{s.tagline}</p>
      </header>
      <h2>{s.pick}</h2>
      <div className="match-grid">
        {matches.map((m) => (
          <button key={m.id} className="match-card" onClick={() => onPick(m.id)}>
            <span className="eyebrow">{s.scenario[m.scenario as keyof Strings['scenario']] ?? m.scenario}</span>
            <span className="mc-row">
              <i style={{ background: m.home.colours[0] }} />
              {m.home.name}
              <b>{m.score[0]}</b>
            </span>
            <span className="mc-row">
              <i style={{ background: m.away.colours[0] }} />
              {m.away.name}
              <b>{m.score[1]}</b>
            </span>
            <span className="muted">{m.venue}</span>
          </button>
        ))}
      </div>
    </main>
  )
}

interface MatchViewProps {
  id: string
  profile: Profile
  onProfile: (p: Profile) => void
  onBack: () => void
  live?: boolean
}

export function MatchView({ id, profile, onProfile, onBack, live: isLive = false }: MatchViewProps) {
  const match = useMatch(id)
  const [speed, setSpeed] = useState(1)
  const [why, setWhy] = useState<Packet | null>(null)
  const [catchUp, setCatchUp] = useState(false)
  const live = useMatchStream(match, profile, speed, isLive)
  const maps = usePitchMaps(match)
  const s = strings(profile.lang)
  if (!match) return <main className="loading">Blindside</main>
  const highlight = live.lowerThird?.data.players?.slice(0, 3) ?? []
  const focus = profile.players[0]
  return (
    <main className="match">
      <header className="topbar">
        <button className="ghost" onClick={onBack}>
          Blindside
        </button>
        <ScoreBug match={match} now={live.now} state={live.state} />
        {isLive && <span className="live-badge">{s.live}</span>}
        <Controls match={match} profile={profile} speed={speed} s={s} onProfile={onProfile} onSpeed={setSpeed} onCatchUp={() => setCatchUp(true)} live={isLive} />
        {!isLive && <Timeline match={match} now={live.now} onSeek={live.seek} />}
      </header>
      <div className="stage">
        <div className="pitch-wrap">
          <Pitch clock={live.clock} {...maps} followed={profile.players} highlight={highlight} tags={live.tags} trails={live.trails} />
          <Cards cards={live.cards} />
          <LowerThird packet={live.lowerThird} match={match} />
          {live.recap && <RecapPanel packet={live.recap} s={s} onClose={live.dismissRecap} />}
          {live.waiting && <div className="waiting">{s.waiting}</div>}
        </div>
        <aside className="side">
          <MatchState match={match} state={live.state} s={s} />
          {focus && <PlayerPanel match={match} pid={focus} now={live.now} s={s} />}
          {profile.mode === 'player_focus' && !focus && <p className="panel muted">{s.pickPlayer}</p>}
          <Feed items={live.feed} s={s} onWhy={setWhy} />
        </aside>
      </div>
      {why && <ReplayModal packet={why} match={match} {...maps} s={s} onClose={() => setWhy(null)} />}
      {catchUp && <CatchUpModal match={match} now={live.now} lang={profile.lang} s={s} onClose={() => setCatchUp(false)} />}
    </main>
  )
}

export function OverlayView({ id, profile, live: isLive = false }: { id: string; profile: Profile; live?: boolean }) {
  const match = useMatch(id)
  const live = useMatchStream(match, profile, 1, isLive)
  if (!match) return null
  return (
    <main className="overlay">
      <ScoreBug match={match} now={live.now} state={live.state} />
      <Cards cards={live.cards} />
      <div className="overlay-tags">
        {live.tags.map((t) => (
          <span key={t.id}>{t.text}</span>
        ))}
      </div>
      <LowerThird packet={live.lowerThird} match={match} />
    </main>
  )
}
