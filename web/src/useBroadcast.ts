import { useEffect, useMemo, useRef, useState } from 'react'
import { api, openBroadcast, type Stream } from './api'
import { MatchClock } from './clock'
import type { Tag, Trail } from './components/Pitch'
import type { FrameMsg, MatchDetail, Packet, Profile, StateMsg, TransportMsg } from './types'

const TRAIL_COLOURS = ['#ffd166', '#ff6b6b', '#3ddc97']

type Timed<T> = T & { period: number; expires: number }

function showing(item: { period: number; expires: number }, now: { period: number; t: number }): boolean {
  return item.period > now.period || (item.period === now.period && item.expires > now.t)
}

const PERSONAS: Record<Profile['mode'], string[]> = {
  fan: ['fan'],
  analyst: ['analyst'],
  player_focus: ['player_focus', 'fan'],
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
          colour: TRAIL_COLOURS[i % TRAIL_COLOURS.length],
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
          setFeed((items) => [p, ...items].slice(0, 40))
          void loadTrails(p)
        } else if (p.slot === 'player_tag') {
          const player = p.data.players?.[0] ?? ''
          setTags((items) => [
            ...items.filter((x) => x.player !== player),
            { id: p.packet, player, text: p.text.headline, period: p.period, expires: p.expires_at },
          ])
        } else if (p.slot === 'panel') {
          setRecap(timed(p))
        } else {
          setCards((items) => [timed(p), ...items].slice(0, 3))
        }
      } else if (msg.kind === 'state') {
        setState(msg as StateMsg)
      } else if (msg.kind === 'clear') {
        clear()
        setFeed([])
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
    play: () => control({ action: 'play' }),
    pause: () => control({ action: 'pause' }),
    setSpeed: (value: number) => control({ action: 'speed', value }),
    seek: (period: number, t: number) => control({ action: 'seek', period, t }),
    dismissRecap: () => setRecap(null),
  }
}

export type Broadcast = ReturnType<typeof useBroadcast>
