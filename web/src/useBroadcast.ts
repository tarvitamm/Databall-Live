import { useEffect, useMemo, useRef, useState } from 'react'
import { api, openBroadcast, type Stream } from './api'
import { MatchClock } from './clock'
import type { Tag, Trail } from './components/Pitch'
import type {
  DetectMsg,
  Detection,
  EventItem,
  EventsMsg,
  FrameMsg,
  HistoryMsg,
  MatchDetail,
  Packet,
  Prediction,
  PredictionResult,
  Profile,
  StateMsg,
  TransportMsg,
} from './types'

export interface Call {
  prompt: Prediction
  result?: PredictionResult
  received: number
  settledAt?: number
}

export interface Score {
  points: number
  streak: number
  best: number
  called: number
  played: number
  last?: { id: string; won: boolean; gained: number }
}

const EMPTY_SCORE: Score = { points: 0, streak: 0, best: 0, called: 0, played: 0 }

function loadScore(): Score {
  try {
    const saved = localStorage.getItem('databall.score')
    return saved ? { ...EMPTY_SCORE, ...(JSON.parse(saved) as Score), last: undefined } : EMPTY_SCORE
  } catch {
    return EMPTY_SCORE
  }
}

type Timed<T> = T & { period: number; expires: number }

function showing(item: { period: number; expires: number }, now: { period: number; t: number }): boolean {
  return item.period > now.period || (item.period === now.period && item.expires > now.t)
}

const PERSONAS: Record<Profile['mode'], string[]> = {
  fan: ['fan'],
  analyst: ['analyst'],
  player_focus: ['player_focus', 'fan'],
}

function newestFirst(a: Packet, b: Packet): number {
  return b.period - a.period || b.show_at - a.show_at
}

function fits(p: Packet, profile: Profile): boolean {
  return p.lang === profile.lang && PERSONAS[profile.mode].includes(p.persona)
}

export function useBroadcast(match: MatchDetail | null, room: string, profile: Profile) {
  const clock = useMemo(() => new MatchClock(), [])
  const stream = useRef<Stream | null>(null)
  const startProfile = useRef(profile)
  const [now, setNow] = useState({ period: 1, t: 0 })
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [lowerThird, setLowerThird] = useState<Timed<{ packet: Packet }> | null>(null)
  const [feed, setFeed] = useState<Packet[]>([])
  const [tags, setTags] = useState<Timed<Tag>[]>([])
  const [cards, setCards] = useState<Timed<{ packet: Packet }>[]>([])
  const [recap, setRecap] = useState<Timed<{ packet: Packet }> | null>(null)
  const [state, setState] = useState<StateMsg | null>(null)
  const [trails, setTrails] = useState<Timed<Trail>[]>([])
  const [detections, setDetections] = useState<{ items: Detection[]; count: number }>({ items: [], count: 0 })
  const [events, setEvents] = useState<{ items: EventItem[]; count: number }>({ items: [], count: 0 })
  const [calls, setCalls] = useState<Record<string, Call>>({})
  const [picks, setPicks] = useState<Record<string, string>>({})
  const picksRef = useRef(picks)
  const [score, setScore] = useState<Score>(loadScore)

  useEffect(() => {
    picksRef.current = picks
  }, [picks])

  useEffect(() => {
    try {
      localStorage.setItem('databall.score', JSON.stringify({ ...score, last: undefined }))
    } catch {
      return
    }
  }, [score])

  useEffect(() => {
    startProfile.current = profile
  }, [profile])

  useEffect(() => {
    if (!match) return
    clock.reset()
    let lastSecond = -1
    const timed = (p: Packet) => ({ packet: p, period: p.period, expires: p.expires_at })
    const clear = () => {
      setLowerThird(null)
      setTags([])
      setCards([])
      setTrails([])
      setRecap(null)
    }
    const loadTrails = async (p: Packet) => {
      if (!p.viz || !p.data.players?.length || !['run_trail', 'chain'].includes(p.viz.kind)) return
      const [start, end] = p.viz.window
      const { frames } = await api.replay(match.id, p.period, start, Math.min(end, p.show_at))
      setTrails(
        p.data.players.slice(0, 3).map((pid, i) => ({
          player: pid,
          points: frames.map((f) => f.players[pid]).filter(Boolean),
          tone: i,
          period: p.period,
          expires: p.expires_at,
        })),
      )
    }
    const s = openBroadcast(match.id, room, startProfile.current, (msg) => {
      if (msg.kind === 'frame') {
        const f = msg as FrameMsg
        clock.push(f)
        const second = Math.floor(f.t)
        if (second !== lastSecond) {
          lastSecond = second
          setNow({ period: f.period, t: f.t })
        }
      } else if (msg.kind === 'hello' || msg.kind === 'transport') {
        const m = msg as TransportMsg
        setPlaying(m.playing)
        setSpeed(m.speed)
      } else if (msg.kind === 'packet') {
        const p = msg as Packet
        if (p.slot === 'lower_third') {
          setLowerThird(timed(p))
          setFeed((items) => [{ ...p, received: Date.now() }, ...items.filter((x) => x.packet !== p.packet)].slice(0, 60))
          void loadTrails(p)
        } else if (p.slot === 'player_tag') {
          const player = p.data.players?.[0] ?? ''
          setTags((items) => [
            ...items.filter((x) => x.player !== player),
            { id: p.packet, player, text: p.text.headline, period: p.period, expires: p.expires_at },
          ])
        } else if (p.slot === 'panel') {
          setRecap(timed({ ...p, received: Date.now() }))
        } else {
          setCards((items) => [timed(p), ...items].slice(0, 3))
        }
      } else if (msg.kind === 'history') {
        const earlier = (msg as HistoryMsg).packets.filter((p) => p.slot === 'lower_third')
        setFeed((items) => {
          const seen = new Set(items.map((p) => p.packet))
          return [...items, ...earlier.filter((p) => !seen.has(p.packet))].sort(newestFirst).slice(0, 60)
        })
      } else if (msg.kind === 'state') {
        setState(msg as StateMsg)
      } else if (msg.kind === 'detect') {
        const m = msg as DetectMsg
        setDetections((d) => ({ items: [...[...m.items].reverse(), ...d.items].slice(0, 8), count: m.count }))
      } else if (msg.kind === 'events') {
        const m = msg as EventsMsg
        setEvents((d) => ({ items: [...[...m.items].reverse(), ...d.items].slice(0, 8), count: m.count }))
      } else if (msg.kind === 'prediction') {
        const m = msg as Prediction
        setCalls((all) => ({ ...all, [m.id]: { prompt: m, received: Date.now() } }))
      } else if (msg.kind === 'prediction_result') {
        const m = msg as PredictionResult
        setCalls((all) => (all[m.id] ? { ...all, [m.id]: { ...all[m.id], result: m, settledAt: Date.now() } } : all))
        const pick = picksRef.current[m.id]
        if (pick) {
          setScore((sc) => {
            const won = pick === m.answer
            const streak = won ? sc.streak + 1 : 0
            const gained = won ? 10 + 5 * (streak - 1) : 0
            return {
              points: sc.points + gained,
              streak,
              best: Math.max(sc.best, streak),
              called: sc.called + (won ? 1 : 0),
              played: sc.played + 1,
              last: { id: m.id, won, gained },
            }
          })
        }
      } else if (msg.kind === 'clear') {
        clear()
        setFeed([])
        setCalls({})
        setDetections({ items: [], count: 0 })
        setEvents({ items: [], count: 0 })
        setPicks({})
      }
    })
    stream.current = s
    return () => {
      s.close()
      clear()
      setFeed([])
      setState(null)
    }
  }, [match, room, clock])

  useEffect(() => {
    stream.current?.send({ kind: 'profile', profile })
  }, [profile])

  const control = (msg: object) => stream.current?.send({ kind: 'control', ...msg })

  return {
    clock,
    now,
    playing,
    speed,
    lowerThird: lowerThird && showing(lowerThird, now) && fits(lowerThird.packet, profile) ? lowerThird.packet : null,
    feed: feed.filter((p) => fits(p, profile)),
    tags: tags.filter((x) => showing(x, now)),
    cards: cards.filter((x) => showing(x, now)).map((x) => x.packet),
    recap: recap && showing(recap, now) && recap.packet.lang === profile.lang ? recap.packet : null,
    state,
    trails: trails.filter((x) => showing(x, now)),
    detections,
    events,
    calls: Object.values(calls).sort((a, b) => b.prompt.period - a.prompt.period || b.prompt.opens - a.prompt.opens),
    picks,
    pick: (id: string, option: string) => setPicks((all) => (all[id] ? all : { ...all, [id]: option })),
    score,
    play: () => control({ action: 'play' }),
    pause: () => control({ action: 'pause' }),
    setSpeed: (value: number) => control({ action: 'speed', value }),
    seek: (period: number, t: number) => control({ action: 'seek', period, t }),
    dismissRecap: () => setRecap(null),
  }
}

export type Broadcast = ReturnType<typeof useBroadcast>
