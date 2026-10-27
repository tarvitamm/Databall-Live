export type Mode = 'fan' | 'analyst' | 'player_focus'
export type View = 'fan' | 'analyst' | 'player' | 'producer'
export type Lang = 'en' | 'es' | 'et'
export type Density = 'low' | 'medium' | 'high'

export interface Team {
  code: string
  name: string
  colours: [string, string]
}

export interface MatchSummary {
  id: string
  scenario: string
  venue: string
  home: Team
  away: Team
  score: [number, number]
  analysed: boolean
}

export interface Player {
  id: string
  name: string
  shirt: number
  position: string
  team: string
}

export interface MatchDetail extends MatchSummary {
  players: Player[]
  periods: Record<string, [number, number]>
}

export interface FrameMsg {
  kind: 'frame'
  t: number
  period: number
  ball: [number, number, number]
  players: Record<string, [number, number]>
}

export interface Packet {
  kind: 'packet'
  packet: string
  insight?: string
  persona: string
  lang: Lang
  slot: 'lower_third' | 'player_tag' | 'pass_card' | 'shot_card' | 'panel' | 'ticker'
  priority: number
  show_at: number
  expires_at: number
  period: number
  text: { headline: string; body?: string }
  data: {
    type?: string
    key?: string
    kind?: string
    teams?: string[]
    players?: string[]
    significance?: number
    confidence?: number
    signals?: Record<string, number | number[]>
    source?: string
    why?: { claim: string; mechanism: string; consequence: string; lang?: string; analyst?: string; storyteller?: string }
  }
  viz?: { kind: string; window: [number, number] }
  received?: number
}

export interface StateMsg {
  kind: 'state'
  period: number
  t: number
  score: Record<string, number>
  xg: Record<string, number>
  label: string
  chaos: number
  control: [number, number]
  momentum: number
  momentum_series: number[]
}

export interface PlayerStats {
  id: string
  distance_km: number
  sprints: number
  top_speed_kmh: number
  runs: Record<string, number>
  decoy_runs: number
  defenders_dragged_m: number
  space_created: number
  pressures: number
  recovery_runs: number
  passes: number
  passes_complete: number
  shots: number
  patterns: { id: string; type: string; period: number; t: number }[]
  season: {
    games: number
    avg: Record<string, number>
    best: Record<string, number>
    totals: { decoy_runs: number; goals: number }
    rank: { decoy_runs: [number, number]; goals: [number, number] }
  } | null
}

export interface Compare {
  minutes: number
  teams: Record<string, { now: Record<string, number>; season: Record<string, number | null>; games: number; form: string }>
}

export interface Prediction {
  kind: 'prediction'
  id: string
  period: number
  opens: number
  closes: number
  question: Record<string, string>
  options: { id: string; label: Record<string, string> }[]
}

export interface PredictionResult {
  kind: 'prediction_result'
  id: string
  period: number
  t: number
  answer: string
  detail: Record<string, string>
}

export interface BoardRow {
  fan: string
  name: string
  points: number
  streak: number
  best: number
  called: number
  played: number
  gained: number
}

export interface LeaderboardMsg {
  kind: 'leaderboard'
  settled: string | null
  rows: BoardRow[]
}

export interface FantasyRow {
  id: string
  team: string
  role: string
  points: number
  items: [string, number, number][]
}

export interface LiveLine {
  period: number
  t: number
  kind: string
  team: string | null
  text: string
}

export type MapKind = 'shots' | 'passes' | 'dribbles' | 'decoys' | 'pressing' | 'attacking' | 'duels' | 'defending'

export interface TeamMaps {
  shots: [number, number, number, string, string][]
  passes: [number, number, number, number, number][]
  dribbles: [number, number, number, number][]
  decoys: [number, number, number, number, string][]
  pressing: [number, number][]
  attacking: [number, number, number, number, number][]
  duels: [number, number, number][]
  defending: [number, number, string][]
}

export interface CatchUp {
  score: Record<string, number>
  xg: Record<string, number>
  moments: { headline: string; body?: string }[]
  state: { label: string; chaos: number; control: [number, number] }
}

export type Metric = '' | 'speed' | 'offball' | 'pressing' | 'chances' | 'passing'

export interface Profile {
  mode: Mode
  lang: Lang
  clubs: string[]
  players: string[]
  density: Density
  metric: Metric
}

export interface TransportMsg {
  kind: 'hello' | 'transport'
  playing: boolean
  speed: number
}

export interface Detection {
  id: string
  type: string
  actor: string | null
  team: string | null
  period: number
  t: number
}

export interface DetectMsg {
  kind: 'detect'
  items: Detection[]
  count: number
}

export interface EventItem {
  id: string
  type: string
  team: string | null
  player: string | null
  recipient?: string | null
  period: number
  t: number
  outcome?: string | null
  distance?: number
  difficulty?: number
  speed?: number
  complete?: boolean
  xg?: number
}

export interface EventsMsg {
  kind: 'events'
  items: EventItem[]
  count: number
}

export interface LiveNumbers {
  teams: Record<string, Record<string, number>>
  leaders: {
    sprint: { player: string; kmh: number }
    distance: { player: string; km: number }
    pass: { player: string; recipient: string | null; difficulty: number; m: number } | null
    shot: { player: string; kmh: number } | null
  }
  rhythm: {
    momentum: [number, number, number][]
    chaos: [number, number, number, string][]
    goals: [number, number, string][]
    periods: Record<string, [number, number]>
  }
}

export interface HistoryMsg {
  kind: 'history'
  packets: Packet[]
}

export type ServerMsg = FrameMsg | Packet | StateMsg | TransportMsg | HistoryMsg | DetectMsg | EventsMsg | Prediction | PredictionResult | LeaderboardMsg | { kind: 'end' | 'clear' }
