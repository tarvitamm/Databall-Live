import { Cards, LowerThird, ScoreBug } from './components/Broadcast'
import { PlayIcon } from './components/Icons'
import { Pitch } from './components/Pitch'
import { clock, type Strings } from './i18n'
import type { PitchMaps } from './pitchMaps'
import type { MatchDetail } from './types'
import type { Broadcast } from './useBroadcast'

function patternName(type: string, s: Strings): string {
  return s.pattern[type] ?? s.patternExtra[type] ?? s.kind[type] ?? type.replace(/_/g, ' ')
}

export function InputPanel({ match, b, maps, s, followed }: { match: MatchDetail; b: Broadcast; maps: PitchMaps; s: Strings; followed: string[] }) {
  const highlight = b.lowerThird?.data.players?.slice(0, 3) ?? []
  return (
    <div className="input-box">
      <div className="monitor-frame">
        <Pitch clock={b.clock} {...maps} followed={followed} highlight={highlight} tags={[]} trails={b.trails} />
        <div className="tv-bug">
          <ScoreBug match={match} now={b.now} state={b.state} />
        </div>
        <span className="cam-chip">
          <i />
          {s.live} · {s.cam}
        </span>
        {!b.playing && (
          <button className="start" onClick={b.play}>
            <PlayIcon />
            {b.now.period === 1 && b.now.t < 1 ? s.startHint : s.play}
          </button>
        )}
      </div>
      <div className="detect">
        <div className="detect-head">
          <span className="eyebrow">{s.detecting}</span>
          <span className="detect-stats">
            {s.tracked} · 10 Hz · <b>{b.detections.count}</b> {s.detections}
          </span>
        </div>
        <ul>
          {b.detections.items.map((d) => (
            <li key={d.id} className={d.team === match.home.code ? 'us' : d.team === match.away.code ? 'opp' : ''}>
              <span className="time">{clock(d.period, d.t)}</span>
              <i />
              <span className="what">{patternName(d.type, s)}</span>
              {d.actor && <span className="who">{maps.names[d.actor] ?? d.actor}</span>}
            </li>
          ))}
        </ul>
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
