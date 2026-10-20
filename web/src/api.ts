import type { CatchUp, FrameMsg, MatchDetail, MatchSummary, PlayerStats, Profile, ServerMsg } from './types'

async function get<T>(path: string, params: Record<string, string | number> = {}): Promise<T> {
  const query = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]))
  const res = await fetch(`${path}${query.size ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`${res.status} ${path}`)
  return res.json() as Promise<T>
}

export const api = {
  matches: () => get<MatchSummary[]>('/api/matches'),
  match: (id: string) => get<MatchDetail>(`/api/matches/${id}`),
  player: (id: string, pid: string, period: number, t: number) =>
    get<PlayerStats>(`/api/matches/${id}/players/${pid}`, { period, t }),
  catchUp: (id: string, period: number, t: number, lang: string) =>
    get<CatchUp>(`/api/matches/${id}/catchup`, { period, t, lang }),
  replay: (id: string, period: number, start: number, end: number) =>
    get<{ frames: FrameMsg[] }>(`/api/matches/${id}/replay`, { period, start, end }),
}

export interface Stream {
  send: (msg: object) => void
  close: () => void
}

export function openStream(
  id: string,
  profile: Profile,
  start: { period: number; t: number; speed: number },
  onMessage: (msg: ServerMsg) => void,
): Stream {
  const params = new URLSearchParams({
    mode: profile.mode,
    lang: profile.lang,
    clubs: profile.clubs.join(','),
    players: profile.players.join(','),
    density: profile.density,
    period: String(start.period),
    t: String(start.t),
    speed: String(start.speed),
  })
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${scheme}://${location.host}/ws/${id}?${params}`)
  ws.onmessage = (ev) => onMessage(JSON.parse(ev.data) as ServerMsg)
  return {
    send: (msg) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(msg)),
    close: () => ws.close(),
  }
}
