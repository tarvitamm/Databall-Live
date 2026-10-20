export type Mode = 'fan' | 'analyst' | 'player_focus'
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
    kind?: string
    teams?: string[]
    players?: string[]
    significance?: number
    confidence?: number
    signals?: Record<string, number | number[]>
  }
  viz?: { kind: string; window: [number, number] }
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
}

export interface CatchUp {
  score: Record<string, number>
  xg: Record<string, number>
  moments: { headline: string; body?: string }[]
  state: { label: string; chaos: number; control: [number, number] }
}

export interface Profile {
  mode: Mode
  lang: Lang
  clubs: string[]
  players: string[]
  density: Density
}

export type ServerMsg = FrameMsg | Packet | StateMsg | { kind: 'hello' | 'end' | 'clear'; playing?: boolean }
