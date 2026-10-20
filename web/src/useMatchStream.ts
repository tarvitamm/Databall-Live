import { useEffect, useMemo, useRef, useState } from 'react'
import { api, openStream, type Stream } from './api'
import { MatchClock } from './clock'
import type { Tag, Trail } from './components/Pitch'
import type { FrameMsg, MatchDetail, Packet, Profile, StateMsg } from './types'

const TRAIL_COLOURS = ['#ffd166', '#ff6b6b', '#3ddc97']

type Timed<T> = T & { period: number; expires: number }

function showing(item: { period: number; expires: number }, now: { period: number; t: number }): boolean {
  return item.period > now.period || (item.period === now.period && item.expires > now.t)
}

export function useMatchStream(match: MatchDetail | null, profile: Profile, speed: number, live = false) {
  const clock = useMemo(() => new MatchClock(), [])
  const stream = useRef<Stream | null>(null)
  const settings = useRef({ profile, speed })
  const [now, setNow] = useState({ period: 1, t: 0 })
  const [lowerThird, setLowerThird] = useState<Timed<{ packet: Packet }> | null>(null)
  const [feed, setFeed] = useState<Packet[]>([])
  const [tags, setTags] = useState<Timed<Tag>[]>([])
  const [cards, setCards] = useState<Timed<{ packet: Packet }>[]>([])
  const [recap, setRecap] = useState<Timed<{ packet: Packet }> | null>(null)
  const [state, setState] = useState<StateMsg | null>(null)
  const [trails, setTrails] = useState<Timed<Trail>[]>([])
  const [ended, setEnded] = useState(false)
  const [waiting, setWaiting] = useState(live)

  useEffect(() => {
    settings.current = { profile, speed }
  }, [profile, speed])

  useEffect(() => {
    if (!match) return
    let lastSecond = -1
    const timed = (p: Packet) => ({ packet: p, period: p.period, expires: p.expires_at })
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
    const { profile: startProfile, speed: startSpeed } = settings.current
    const s = openStream(match.id, startProfile, { period: 1, t: 0, speed: startSpeed }, (msg) => {
      if (msg.kind === 'frame') {
        setWaiting(false)
        const f = msg as FrameMsg
        clock.push(f)
        const second = Math.floor(f.t)
        if (second !== lastSecond) {
          lastSecond = second
          setNow({ period: f.period, t: f.t })
        }
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
      } else if (msg.kind === 'end') {
        setEnded(true)
      } else if (msg.kind === 'clear') {
        setLowerThird(null)
        setTags([])
        setCards([])
        setTrails([])
        setRecap(null)
      }
    }, live)
    stream.current = s
    return () => s.close()
  }, [match, clock, live])

  useEffect(() => {
    stream.current?.send({ kind: 'profile', profile })
  }, [profile])

  useEffect(() => {
    stream.current?.send({ kind: 'speed', speed })
  }, [speed])

  const seek = (period: number, t: number) => {
    stream.current?.send({ kind: 'seek', period, t })
    setFeed([])
    setLowerThird(null)
    setTags([])
    setTrails([])
    setCards([])
  }

  return {
    clock,
    now,
    lowerThird: lowerThird && showing(lowerThird, now) ? lowerThird.packet : null,
    feed,
    tags: tags.filter((x) => showing(x, now)),
    cards: cards.filter((x) => showing(x, now)).map((x) => x.packet),
    recap: recap && showing(recap, now) ? recap.packet : null,
    state,
    trails: trails.filter((x) => showing(x, now)),
    ended,
    waiting,
    seek,
    dismissRecap: () => setRecap(null),
  }
}
