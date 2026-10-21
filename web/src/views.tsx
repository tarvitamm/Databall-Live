import { Cards, LowerThird, ScoreBug } from './components/Broadcast'
import { PlayIcon } from './components/Icons'
import { Pitch } from './components/Pitch'
import type { Strings } from './i18n'
import type { PitchMaps } from './pitchMaps'
import type { MatchDetail } from './types'
import type { Broadcast } from './useBroadcast'

export function InputPanel({ match, b, maps, s, followed }: { match: MatchDetail; b: Broadcast; maps: PitchMaps; s: Strings; followed: string[] }) {
  const highlight = b.lowerThird?.data.players?.slice(0, 3) ?? []
  return (
    <div className="input-box">
      <div className="pitch-card">
        <Pitch clock={b.clock} {...maps} followed={followed} highlight={highlight} tags={[]} trails={b.trails} />
        {!b.playing && (
          <button className="start" onClick={b.play}>
            <PlayIcon />
            {b.now.period === 1 && b.now.t < 1 ? s.startHint : s.play}
          </button>
        )}
      </div>
      <div className="legend">
        <span>
          <i className="team-us" />
          {match.home.name}
        </span>
        <span>
          <i className="team-opp" />
          {match.away.name}
        </span>
        <span>
          <i className="ring" />
          {s.ringed}
        </span>
      </div>
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
