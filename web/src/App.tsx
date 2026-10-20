import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { ScoreBug } from './components/Broadcast'
import { Timeline } from './components/Timeline'
import { strings, type Strings } from './i18n'
import { ProducerView } from './producer'
import type { Lang, MatchDetail, MatchSummary, Profile, View } from './types'
import { useBroadcast } from './useBroadcast'
import { usePitchMaps } from './pitchMaps'
import { AnalystView, FanView, OverlayView, PlayerView } from './views'

const VIEWS: View[] = ['fan', 'analyst', 'player', 'producer']
const LANGS: Lang[] = ['en', 'es', 'et']
const SPEEDS = [1, 2, 5, 10]
const STAR = 'HAR_7'

function stored(key: string): string | null {
  try {
    return localStorage.getItem(`blindside.${key}`)
  } catch {
    return null
  }
}

function store(key: string, value: string): void {
  try {
    localStorage.setItem(`blindside.${key}`, value)
  } catch {
    return
  }
}

function initialRoom(query: URLSearchParams): string {
  const room = query.get('room') ?? stored('room') ?? Math.random().toString(36).slice(2, 10)
  store('room', room)
  return room
}

function tabLabel(view: View, s: Strings): string {
  return { fan: s.fan, analyst: s.analyst, player: s.player_focus, producer: s.producer }[view]
}

function defaultPlayer(match: MatchDetail | null): string {
  if (!match) return ''
  if (match.players.some((p) => p.id === STAR)) return STAR
  const forward = match.players.find((p) => p.team === match.home.code && ['ST', 'RW', 'LW', 'AM'].includes(p.position))
  return forward?.id ?? match.players[0]?.id ?? ''
}

export default function App() {
  const query = useMemo(() => new URLSearchParams(location.search), [])
  const overlay = query.get('view') === 'overlay'
  const [matches, setMatches] = useState<MatchSummary[]>([])
  const [chosen, setChosen] = useState<string | null>(query.get('match') ?? stored('match'))
  const [view, setView] = useState<View>(VIEWS.includes(query.get('view') as View) ? (query.get('view') as View) : 'fan')
  const [lang, setLang] = useState<Lang>((query.get('lang') ?? stored('lang') ?? 'en') as Lang)
  const [club, setClub] = useState('')
  const [picked, setPicked] = useState(query.get('player') ?? '')
  const [room] = useState(() => initialRoom(query))
  const [match, setMatch] = useState<MatchDetail | null>(null)

  useEffect(() => {
    api.matches().then(setMatches)
  }, [])

  const id = chosen && (matches.length === 0 || matches.some((m) => m.id === chosen)) ? chosen : (matches[0]?.id ?? null)

  useEffect(() => {
    if (!id) return
    let live = true
    api.match(id).then((m) => live && setMatch(m))
    return () => {
      live = false
    }
  }, [id])

  useEffect(() => {
    if (!id || overlay) return
    store('match', id)
    store('lang', lang)
    const url = new URL(location.href)
    url.searchParams.set('match', id)
    url.searchParams.set('view', view)
    url.searchParams.set('lang', lang)
    history.replaceState(null, '', url)
  }, [id, view, lang, overlay])

  const current = match?.id === id ? match : null
  const player = picked && current?.players.some((p) => p.id === picked) ? picked : defaultPlayer(current)
  const profile = useMemo<Profile>(
    () => ({
      mode: view === 'analyst' ? 'analyst' : view === 'player' ? 'player_focus' : 'fan',
      lang,
      clubs: view === 'fan' && club ? [club] : [],
      players: view === 'player' && player ? [player] : [],
      density: view === 'analyst' ? 'high' : 'medium',
    }),
    [view, lang, club, player],
  )
  const b = useBroadcast(current, room, profile)
  const maps = usePitchMaps(current)
  const s = strings(lang)

  if (overlay) return current ? <OverlayView match={current} b={b} /> : null

  const pickMatch = (next: string) => {
    setChosen(next)
    setClub('')
    setPicked('')
  }

  return (
    <div className="app">
      <header className="shell-head">
        <span className="brand-mark">Blindside</span>
        <select className="match-select" value={id ?? ''} onChange={(e) => pickMatch(e.target.value)} aria-label={s.pick}>
          {matches.map((m) => (
            <option key={m.id} value={m.id}>
              {m.home.name} v {m.away.name} · {s.scenario[m.scenario as keyof Strings['scenario']] ?? m.scenario}
            </option>
          ))}
        </select>
        <nav className="tabs">
          {VIEWS.map((v) => (
            <button key={v} className={view === v ? 'on' : ''} onClick={() => setView(v)}>
              {tabLabel(v, s)}
            </button>
          ))}
        </nav>
        <div className="segmented small langs">
          {LANGS.map((l) => (
            <button key={l} className={lang === l ? 'on' : ''} onClick={() => setLang(l)}>
              {l.toUpperCase()}
            </button>
          ))}
        </div>
      </header>

      {current ? (
        <>
          <div className="matchbar">
            <ScoreBug match={current} now={b.now} state={b.state} />
            <button className="primary" onClick={b.playing ? b.pause : b.play}>
              {b.playing ? s.pause : s.play}
            </button>
            <div className="segmented small">
              {SPEEDS.map((v) => (
                <button key={v} className={b.speed === v ? 'on' : ''} onClick={() => b.setSpeed(v)}>
                  {v}x
                </button>
              ))}
            </div>
            <Timeline match={current} now={b.now} onSeek={b.seek} />
          </div>
          {view === 'fan' && <FanView match={current} b={b} maps={maps} s={s} lang={lang} club={club} onClub={setClub} />}
          {view === 'analyst' && <AnalystView match={current} b={b} maps={maps} s={s} lang={lang} />}
          {view === 'player' && <PlayerView match={current} b={b} maps={maps} s={s} lang={lang} player={player} onPlayer={setPicked} />}
          {view === 'producer' && <ProducerView match={current} room={room} b={b} maps={maps} s={s} />}
        </>
      ) : (
        <main className="loading">Blindside</main>
      )}
    </div>
  )
}
