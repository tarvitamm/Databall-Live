import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { badgeFor } from './badges'
import { AnalystDesk } from './components/AnalystDesk'
import { Mark, PauseIcon, PlayIcon } from './components/Icons'
import { FanApp, PlayerApp } from './components/MobileApp'
import { Timeline, type Mark as TimelineMark } from './components/Timeline'
import { strings, type Strings } from './i18n'
import { usePitchMaps } from './pitchMaps'
import { ProducerDesk } from './producer'
import { useTheme } from './theme'
import type { Lang, MatchDetail, MatchSummary, Profile, View } from './types'
import { useBroadcast } from './useBroadcast'
import { InputPanel, OverlayView } from './views'

const VIEWS: View[] = ['fan', 'analyst', 'player', 'producer']
const LANGS: Lang[] = ['en', 'es', 'et']
const SPEEDS = [1, 2, 5, 10]
const STAR = 'HAR_7'

function stored(key: string): string | null {
  try {
    return localStorage.getItem(`databall.${key}`)
  } catch {
    return null
  }
}

function store(key: string, value: string): void {
  try {
    localStorage.setItem(`databall.${key}`, value)
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

function outputLabel(view: View, s: Strings): string {
  return { fan: s.outFan, analyst: s.outAnalyst, player: s.outPlayer, producer: s.outProducer }[view]
}

function defaultPlayer(match: MatchDetail | null): string {
  if (!match) return ''
  if (match.players.some((p) => p.id === STAR)) return STAR
  const forward = match.players.find((p) => p.team === match.home.code && ['ST', 'RW', 'LW', 'AM'].includes(p.position))
  return forward?.id ?? match.players[0]?.id ?? ''
}

export default function App() {
  const theme = useTheme()
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
    let live = true
    let timer = 0
    const load = () =>
      api
        .matches()
        .then((m) => live && setMatches(m))
        .catch(() => {
          if (live) timer = window.setTimeout(load, 1500)
        })
    load()
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [])

  const id = chosen && (matches.length === 0 || matches.some((m) => m.id === chosen)) ? chosen : (matches[0]?.id ?? null)

  useEffect(() => {
    if (!id) return
    let live = true
    let timer = 0
    const load = () =>
      api
        .match(id)
        .then((m) => live && setMatch(m))
        .catch(() => {
          if (live) timer = window.setTimeout(load, 1500)
        })
    load()
    return () => {
      live = false
      clearTimeout(timer)
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

  const props = { match: current!, b, maps, s, lang }
  const marks: TimelineMark[] = b.feed.map((p) => {
    const badge = badgeFor(p, s)?.tone
    const team = p.data.teams?.[0]
    return { id: p.packet, period: p.period, t: p.show_at, tone: badge ?? (team === current?.home.code ? 'us' : 'opp') }
  })

  return (
    <div className="app">
      <header className="topline">
        <span className="brand">
          <Mark size={20} />
          <span className="wordmark">
            Databall <b>Live</b>
          </span>
          <span className="div" aria-hidden />
          <select className="match-select" value={id ?? ''} onChange={(e) => pickMatch(e.target.value)} aria-label={s.pick}>
            {matches.map((m) => (
              <option key={m.id} value={m.id}>
                {m.home.name} v {m.away.name} · {s.scenario[m.scenario as keyof Strings['scenario']] ?? m.scenario}
              </option>
            ))}
          </select>
        </span>
        <nav className="tabs views">
          {VIEWS.map((v) => (
            <button key={v} className={view === v ? 'on' : ''} onClick={() => setView(v)}>
              {tabLabel(v, s)}
            </button>
          ))}
        </nav>
        <span className="actions">
          <span className="tabs">
            {LANGS.map((l) => (
              <button key={l} className={lang === l ? 'on' : ''} onClick={() => setLang(l)}>
                {l.toUpperCase()}
              </button>
            ))}
          </span>
          <button className="pill" onClick={theme.toggle}>
            {s.theme}
          </button>
        </span>
      </header>

      {current ? (
        <>
          <div className="fbar">
            <button className="play" onClick={b.playing ? b.pause : b.play} aria-label={b.playing ? s.pause : s.play}>
              {b.playing ? <PauseIcon /> : <PlayIcon />}
            </button>
            <span className="tabs">
              {SPEEDS.map((v) => (
                <button key={v} className={b.speed === v ? 'on' : ''} onClick={() => b.setSpeed(v)}>
                  {v}x
                </button>
              ))}
            </span>
            <Timeline match={current} now={b.now} marks={marks} onSeek={b.seek} />
          </div>
          <main className="io">
            <section className="io-col">
              <div className="io-label">
                <span className="step">01</span>
                <h2>{s.input}</h2>
                <span className="eyebrow">{s.inputSub}</span>
              </div>
              <InputPanel {...props} followed={view === 'player' && player ? [player] : []} />
            </section>
            <section className="io-col">
              <div className="io-label">
                <span className="step">02</span>
                <h2>{s.output}</h2>
                <span className="eyebrow">{outputLabel(view, s)}</span>
              </div>
              <div className={`output-box ${view}`}>
                {view === 'fan' && <FanApp {...props} club={club} onClub={setClub} />}
                {view === 'analyst' && <AnalystDesk {...props} />}
                {view === 'player' && <PlayerApp {...props} player={player} onPlayer={setPicked} />}
                {view === 'producer' && <ProducerDesk {...props} room={room} />}
              </div>
            </section>
          </main>
        </>
      ) : (
        <main className="loading">Databall Live</main>
      )}
    </div>
  )
}
