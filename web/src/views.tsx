import { useState } from 'react'
import { Cards, LowerThird, ScoreBug } from './components/Broadcast'
import { PlayIcon } from './components/Icons'
import { Pitch } from './components/Pitch'
import { clock, type Strings } from './i18n'
import type { PitchMaps } from './pitchMaps'
import type { EventItem, MatchDetail } from './types'
import type { Broadcast } from './useBroadcast'

function patternName(type: string, s: Strings): string {
  return s.pattern[type] ?? s.patternExtra[type] ?? s.kind[type] ?? type.replace(/_/g, ' ')
}

function fill(text: string, values: Record<string, string | number>): string {
  return text.replace(/\{(\w+)\}/g, (_, k: string) => String(values[k] ?? ''))
}

function eventDetail(e: EventItem, s: Strings, maps: PitchMaps, match: MatchDetail, lang: string): string {
  const num = (v: number, d = 0) => (lang === 'en' ? v.toFixed(d) : v.toFixed(d).replace('.', ','))
  if (e.type === 'pass' && e.distance !== undefined) {
    const to = e.recipient ? ` → ${maps.names[e.recipient] ?? ''}` : ''
    return `${to} · ${fill(s.evPass, { d: e.distance, x: num(e.difficulty ?? 0, 1) })}`
  }
  if (e.type === 'shot' && e.speed !== undefined) return ` · ${fill(s.evShot, { v: e.speed, xg: num(e.xg ?? 0, 2) })}`
  if (e.type === 'possession') return ` · ${fill(s.evWin, { team: e.team === match.home.code ? match.home.name : match.away.name })}`
  return ''
}

interface InputProps {
  match: MatchDetail
  b: Broadcast
  maps: PitchMaps
  s: Strings
  lang: string
  followed: string[]
}

export function InputPanel({ match, b, maps, s, lang, followed }: InputProps) {
  const [names, setNames] = useState(false)
  const highlight = b.lowerThird?.data.players?.slice(0, 3) ?? []
  const side = (team: string | null) => (team === match.home.code ? 'us' : team === match.away.code ? 'opp' : '')
  return (
    <div className="input-box">
      <div className="monitor-frame">
        <Pitch clock={b.clock} {...maps} followed={followed} highlight={highlight} tags={[]} trails={b.trails} showNames={names} />
        <div className="tv-bug">
          <ScoreBug match={match} now={b.now} state={b.state} />
        </div>
        <span className="cam-chip">
          <i />
          {s.live} · {s.cam}
        </span>
        <button className={`names-toggle ${names ? 'on' : ''}`} onClick={() => setNames(!names)}>
          {s.names}
        </button>
        {!b.playing && (
          <button className="start" onClick={b.play}>
            <PlayIcon />
            {b.now.period === 1 && b.now.t < 1 ? s.startHint : s.play}
          </button>
        )}
      </div>
      <div className="streams">
        <div className="detect">
          <div className="detect-head">
            <span className="eyebrow">{s.eventsIn}</span>
            <span className="detect-stats">
              {s.tracked} · 10 Hz · <b>{b.events.count}</b>
            </span>
          </div>
          <ul>
            {b.events.items.map((e) => (
              <li key={e.id} className={`${side(e.team)} ${e.type === 'possession' ? 'flip' : ''}`}>
                <span className="time">{clock(e.period, e.t)}</span>
                <i />
                <span className="what">
                  {s.ev[e.type] ?? e.type}
                  {e.player && <b> {maps.names[e.player] ?? e.player}</b>}
                  <span className="muted">{eventDetail(e, s, maps, match, lang)}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="detect">
          <div className="detect-head">
            <span className="eyebrow">{s.detecting}</span>
            <span className="detect-stats">
              <b>{b.detections.count}</b> {s.detections}
            </span>
          </div>
          <ul>
            {b.detections.items.map((d) => (
              <li key={d.id} className={side(d.team)}>
                <span className="time">{clock(d.period, d.t)}</span>
                <i />
                <span className="what">{patternName(d.type, s)}</span>
                {d.actor && <span className="who">{maps.names[d.actor] ?? d.actor}</span>}
              </li>
            ))}
          </ul>
        </div>
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
