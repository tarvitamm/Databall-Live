import type { Strings } from './i18n'
import type { PitchMaps } from './pitchMaps'
import type { FrameMsg, Lang, MatchDetail, Packet } from './types'

export type Tone = 'us' | 'opp' | 'ink' | 'warn'
type P2 = [number, number]

export type SceneMark =
  | { kind: 'circle'; at: P2; r: number; tone: Tone; dashed?: boolean; n?: number }
  | { kind: 'line'; a: P2; b: P2; tone: Tone; dashed?: boolean; arrow?: boolean; n?: number }
  | { kind: 'path'; pts: P2[]; tone: Tone; dashed?: boolean; n?: number }

export interface SceneItem {
  n: number
  label: string
  value: string
}

export interface SceneLabel {
  id: string
  role: string
  tone: Tone
}

export interface Measure {
  items: SceneItem[]
  marks: SceneMark[]
  labels: SceneLabel[]
  focus: P2
}

export interface SceneSpec {
  title: string
  subtitle: string
  tone: Tone
  players: string[]
  measure: (frames: FrameMsg[], k: number) => Measure
}

interface Ctx {
  match: MatchDetail
  packet: Packet
  maps: PitchMaps
  s: Strings
  lang: Lang
  fan: boolean
}

const dist = (a: P2, b: P2) => Math.hypot(a[0] - b[0], a[1] - b[1])

function fmt(v: number, lang: Lang, d = 0): string {
  const text = v.toFixed(d)
  return lang === 'en' ? text : text.replace('.', ',')
}

function fill(text: string, values: Record<string, string | number>): string {
  return text.replace(/\{(\w+)\}/g, (_, k: string) => String(values[k] ?? ''))
}

function tone(team: number): Tone {
  return team === 0 ? 'us' : 'opp'
}

function ids(c: Ctx, f: FrameMsg, team: number, keeper = true): string[] {
  return Object.keys(f.players).filter((id) => c.maps.teamOf[id] === team && (keeper || c.maps.shirts[id] !== 1))
}

function nearest(f: FrameMsg, pool: string[], to: P2, skip?: string): string | null {
  let best: string | null = null
  let d = Infinity
  for (const id of pool) {
    if (id === skip) continue
    const e = dist(f.players[id], to)
    if (e < d) {
      d = e
      best = id
    }
  }
  return best
}

function teamName(c: Ctx, team: number): string {
  return team === 0 ? c.match.home.name : c.match.away.name
}

function teamIndex(c: Ctx, code: string | undefined): number {
  return code === c.match.away.code ? 1 : 0
}

function path(frames: FrameMsg[], k: number, id: string): P2[] {
  return frames.slice(0, k + 1).map((f) => f.players[id]).filter(Boolean)
}

function length(pts: P2[]): number {
  return pts.slice(1).reduce((sum, p, i) => sum + dist(p, pts[i]), 0)
}

function topSpeed(pts: P2[]): number {
  let best = 0
  for (let i = 3; i < pts.length; i++) best = Math.max(best, (dist(pts[i], pts[i - 3]) / 0.6) * 3.6)
  return best
}

/** The nearest player, but keep the previous pick unless someone is clearly closer, so roles do not flicker. */
function sticky(f: FrameMsg, pool: string[], to: P2, prev: string | null): string | null {
  const best = nearest(f, pool, to)
  if (prev && best && pool.includes(prev) && dist(f.players[prev], to) <= dist(f.players[best], to) + 2.5) return prev
  return best
}

function press(c: Ctx, fixed: number | null): SceneSpec {
  const t = c.s.scene
  const pressing0 = fixed ?? 0
  let held: string | null = null
  let heldPresser: string | null = null
  let peak = 0
  let lastK = 0
  return {
    title: fill(t.press, { team: teamName(c, pressing0) }),
    subtitle: fill(t.inPossession, { team: teamName(c, 1 - pressing0) }),
    tone: tone(pressing0),
    players: [],
    measure: (frames, k) => {
      const f = frames[k]
      const ball: P2 = [f.ball[0], f.ball[1]]
      const near = nearest(f, Object.keys(f.players), ball)
      const pressing = fixed ?? (near ? 1 - (c.maps.teamOf[near] ?? 0) : 0)
      const poss = 1 - pressing
      const carrier = sticky(f, ids(c, f, poss), ball, held)
      held = carrier
      if (!carrier) return { items: [], marks: [], labels: [], focus: ball }
      const at = f.players[carrier]
      const defenders = ids(c, f, pressing, false)
      const pressers = defenders.filter((id) => dist(f.players[id], at) <= 10)
      peak = k < lastK ? pressers.length : Math.max(peak, pressers.length)
      lastK = k
      const closest = sticky(f, defenders, at, heldPresser)
      heldPresser = closest
      const mate = closest ? nearest(f, defenders, f.players[closest], closest) : null
      const xs = defenders.map((id) => f.players[id][0])
      const ys = defenders.map((id) => f.players[id][1])
      const yMid = ys.reduce((a, b) => a + b, 0) / Math.max(ys.length, 1)
      const outlets = ids(c, f, poss, false).filter(
        (id) => id !== carrier && dist(f.players[id], at) <= 15 && defenders.every((d) => dist(f.players[d], f.players[id]) > 3),
      )
      const marks: SceneMark[] = [{ kind: 'circle', at, r: 10, tone: tone(pressing), dashed: true, n: 1 }]
      if (closest && mate) marks.push({ kind: 'line', a: f.players[closest], b: f.players[mate], tone: 'ink', dashed: true, n: 2 })
      marks.push({ kind: 'line', a: [Math.min(...xs), yMid], b: [Math.max(...xs), yMid], tone: tone(pressing), n: 3 })
      outlets.forEach((id, i) => marks.push({ kind: 'line', a: at, b: f.players[id], tone: tone(poss), arrow: true, n: i === 0 ? 4 : undefined }))
      const labels: SceneLabel[] = [{ id: carrier, role: t.carrier, tone: tone(poss) }]
      if (closest) labels.push({ id: closest, role: t.presser, tone: tone(pressing) })
      return {
        focus: at,
        marks,
        labels,
        items: c.fan ? [
          { n: 1, label: fill(c.s.sceneFan.pressHunt, { n: peak }), value: '' },
          { n: 2, label: fill(c.s.sceneFan.pressLead, { name: closest ? (c.maps.names[closest] ?? '') : '' }), value: '' },
          { n: 3, label: outlets.length ? fill(c.s.sceneFan.pressOutlets, { n: outlets.length }) : c.s.sceneFan.pressTrapped, value: '' },
        ] : [
          { n: 1, label: t.density, value: fill(t.densityV, { n: pressers.length }) },
          { n: 2, label: t.support, value: fill(t.supportV, { d: closest && mate ? fmt(dist(f.players[closest], f.players[mate]), c.lang, 1) : '-' }) },
          { n: 3, label: t.depth, value: fill(t.depthV, { d: fmt(Math.max(...xs) - Math.min(...xs), c.lang) }) },
          { n: 4, label: t.outlets, value: fill(t.outletsV, { n: outlets.length }) },
        ],
      }
    },
  }
}

function decoy(c: Ctx): SceneSpec {
  const t = c.s.scene
  const [runner, defender, benef] = c.packet.data.players ?? []
  const team = c.maps.teamOf[runner] ?? 0
  return {
    title: fill(t.decoy, { name: c.maps.names[runner] ?? runner }),
    subtitle: fill(t.inPossession, { team: teamName(c, team) }),
    tone: tone(team),
    players: [runner, defender, benef].filter(Boolean),
    measure: (frames, k) => {
      const f = frames[k]
      const run = path(frames, k, runner)
      const follow = defender ? path(frames, k, defender) : []
      const start = follow[0] ?? run[0]
      const cover = ids(c, f, 1 - team, false)
      const gap = start ? Math.min(...cover.map((id) => dist(f.players[id], start))) : 0
      const marks: SceneMark[] = [{ kind: 'path', pts: run, tone: tone(team), n: 1 }]
      if (follow.length > 1) marks.push({ kind: 'path', pts: follow, tone: tone(1 - team), dashed: true, n: 2 })
      if (start) marks.push({ kind: 'circle', at: start, r: 5, tone: 'warn', dashed: true, n: 3 })
      const receiver = benef ? path(frames, k, benef) : []
      if (receiver.length > 1) marks.push({ kind: 'line', a: receiver[0], b: receiver[receiver.length - 1], tone: tone(team), arrow: true, n: 4 })
      const labels: SceneLabel[] = [{ id: runner, role: t.rolDecoy, tone: tone(team) }]
      if (defender) labels.push({ id: defender, role: t.rolDragged, tone: tone(1 - team) })
      if (benef) labels.push({ id: benef, role: t.rolReceiver, tone: tone(team) })
      const here = f.players[runner] ?? start
      return {
        focus: start && here ? [(here[0] + start[0]) / 2, (here[1] + start[1]) / 2] : here,
        marks,
        labels,
        items: c.fan ? [
          { n: 1, label: fill(c.s.sceneFan.decoyRun, { name: c.maps.names[runner] ?? '', d: fmt(length(run), c.lang) }), value: '' },
          { n: 2, label: fill(c.s.sceneFan.decoyFollow, { name: c.maps.names[defender] ?? '' }), value: '' },
          { n: 3, label: fill(c.s.sceneFan.decoyGap, { d: fmt(gap, c.lang) }), value: '' },
          { n: 4, label: fill(c.s.sceneFan.decoyUse, { name: c.maps.names[benef] ?? '' }), value: '' },
        ] : [
          { n: 1, label: t.run, value: fill(t.runV, { d: fmt(length(run), c.lang), v: fmt(topSpeed(run), c.lang, 1) }) },
          { n: 2, label: t.dragged, value: fill(t.draggedV, { name: c.maps.names[defender] ?? '-', d: fmt(length(follow), c.lang) }) },
          { n: 3, label: t.space, value: fill(t.spaceV, { d: fmt(gap, c.lang, 1) }) },
          { n: 4, label: t.receiver, value: fill(t.receiverV, { name: c.maps.names[benef] ?? '-' }) },
        ],
      }
    },
  }
}

function chance(c: Ctx): SceneSpec {
  const t = c.s.scene
  const [shooter, decoyRunner] = c.packet.data.players ?? []
  const team = c.maps.teamOf[shooter] ?? 0
  const sig = c.packet.data.signals ?? {}
  return {
    title: fill(t.chance, { team: teamName(c, team) }),
    subtitle: c.packet.text.headline,
    tone: tone(team),
    players: [shooter, decoyRunner].filter(Boolean),
    measure: (frames, k) => {
      const ball: P2[] = []
      for (const f of frames.slice(0, k + 1)) {
        const at: P2 = [f.ball[0], f.ball[1]]
        const last = ball[ball.length - 1]
        if (last && dist(at, last) > 15) break
        ball.push(at)
        if (at[0] <= 0 || at[0] >= 105) break
      }
      const marks: SceneMark[] = [{ kind: 'path', pts: ball, tone: 'ink', dashed: true, n: 1 }]
      const labels: SceneLabel[] = [{ id: shooter, role: t.shooter, tone: tone(team) }]
      const xg = Number(sig.xg ?? 0)
      const fanItems: SceneItem[] = [
        { n: 1, label: fill(Number(sig.passes ?? 0) ? c.s.sceneFan.chanceBuild : c.s.sceneFan.chanceSolo, { n: Number(sig.passes ?? 0), s: fmt(Number(sig.seconds ?? 0), c.lang) }), value: '' },
        { n: 2, label: fill(c.s.sceneFan.chanceShot, { name: c.maps.names[shooter] ?? '' }), value: '' },
        { n: 3, label: xg >= 0.4 ? c.s.sceneFan.chanceBig : fill(c.s.sceneFan.chanceOdds, { odds: Math.max(2, Math.round(1 / Math.max(xg, 0.01))) }), value: '' },
      ]
      if (decoyRunner) fanItems.push({ n: 4, label: fill(c.s.sceneFan.chanceDecoy, { name: c.maps.names[decoyRunner] ?? '' }), value: '' })
      const items: SceneItem[] = [
        { n: 1, label: t.ballPath, value: fill(t.ballPathV, { d: fmt(length(ball), c.lang) }) },
        { n: 2, label: t.build, value: fill(t.buildV, { n: Number(sig.passes ?? 0), s: fmt(Number(sig.seconds ?? 0), c.lang) }) },
        { n: 3, label: t.quality, value: fill(t.qualityV, { xg: fmt(Number(sig.xg ?? 0), c.lang, 2) }) },
      ]
      if (decoyRunner) {
        marks.push({ kind: 'path', pts: path(frames, k, decoyRunner), tone: tone(team), n: 4 })
        labels.push({ id: decoyRunner, role: t.rolDecoy, tone: tone(team) })
        items.push({ n: 4, label: t.run, value: fill(t.decoyHelp, { name: c.maps.names[decoyRunner] ?? '' }) })
      }
      return { focus: ball[ball.length - 1] ?? [52.5, 34], marks, labels, items: c.fan ? fanItems : items }
    },
  }
}

function lines(c: Ctx): SceneSpec {
  const t = c.s.scene
  const [receiver] = c.packet.data.players ?? []
  const attack = c.maps.teamOf[receiver] ?? 0
  const def = 1 - attack
  return {
    title: t.gapT,
    subtitle: fill(t.inPossession, { team: teamName(c, attack) }),
    tone: tone(attack),
    players: [receiver].filter(Boolean),
    measure: (frames, k) => {
      const f = frames[k]
      const keeper = ids(c, f, def).find((id) => c.maps.shirts[id] === 1)
      const goalX = keeper ? f.players[keeper][0] : def === 0 ? 0 : 105
      const out = ids(c, f, def, false).sort((a, b) => Math.abs(f.players[a][0] - goalX) - Math.abs(f.players[b][0] - goalX))
      const back = out.slice(0, 4).map((id) => f.players[id]).sort((a, b) => a[1] - b[1])
      const mid = out.slice(4, 8).map((id) => f.players[id]).sort((a, b) => a[1] - b[1])
      const mean = (pts: P2[]) => pts.reduce((s2, p) => s2 + p[0], 0) / Math.max(pts.length, 1)
      const at = f.players[receiver] ?? [52.5, 34]
      const gap = Math.abs(mean(mid) - mean(back))
      return {
        focus: at,
        marks: [
          { kind: 'path', pts: back, tone: tone(def), n: 1 },
          { kind: 'path', pts: mid, tone: tone(def), dashed: true, n: 2 },
          { kind: 'line', a: [mean(back), at[1]], b: [mean(mid), at[1]], tone: 'warn', n: 3 },
        ],
        labels: receiver ? [{ id: receiver, role: t.pocket, tone: tone(attack) }] : [],
        items: c.fan ? [
          { n: 1, label: fill(c.s.sceneFan.gapLines, { d: fmt(gap, c.lang) }), value: '' },
          { n: 2, label: fill(c.s.sceneFan.gapPocket, { name: c.maps.names[receiver] ?? '' }), value: '' },
        ] : [
          { n: 1, label: t.backLine, value: fill(t.fromGoal, { d: fmt(Math.abs(mean(back) - goalX), c.lang) }) },
          { n: 2, label: t.midLine, value: fill(t.fromGoal, { d: fmt(Math.abs(mean(mid) - goalX), c.lang) }) },
          { n: 3, label: t.gap, value: fill(t.gapV, { d: fmt(gap, c.lang, 1) }) },
        ],
      }
    },
  }
}

function overload(c: Ctx): SceneSpec {
  const t = c.s.scene
  const team = teamIndex(c, c.packet.data.teams?.[0])
  return {
    title: fill(t.overloadT, { team: teamName(c, team) }),
    subtitle: c.packet.text.headline,
    tone: tone(team),
    players: [],
    measure: (frames, k) => {
      const f = frames[k]
      const ball: P2 = [f.ball[0], f.ball[1]]
      const attackers = ids(c, f, team).filter((id) => dist(f.players[id], ball) <= 12)
      const defenders = ids(c, f, 1 - team).filter((id) => dist(f.players[id], ball) <= 12)
      const marks: SceneMark[] = [{ kind: 'circle', at: ball, r: 12, tone: tone(team), dashed: true, n: 1 }]
      attackers.forEach((id) => marks.push({ kind: 'line', a: ball, b: f.players[id], tone: tone(team) }))
      return {
        focus: ball,
        marks,
        labels: [],
        items: c.fan ? [
          { n: 1, label: fill(c.s.sceneFan.overload, { a: attackers.length, d: defenders.length }), value: '' },
        ] : [
          { n: 1, label: t.around, value: fill(t.aroundV, { a: attackers.length, d: defenders.length }) },
          { n: 2, label: t.support, value: fill(t.supportV, { d: attackers.length > 1 ? fmt(Math.min(...attackers.slice(1).map((id) => dist(f.players[id], f.players[attackers[0]]))), c.lang, 1) : '-' }) },
        ],
      }
    },
  }
}

function sprint(c: Ctx): SceneSpec {
  const t = c.s.scene
  const [player] = c.packet.data.players ?? []
  const team = c.maps.teamOf[player] ?? 0
  return {
    title: fill(t.sprintT, { name: c.maps.names[player] ?? player }),
    subtitle: c.packet.text.headline,
    tone: tone(team),
    players: [player].filter(Boolean),
    measure: (frames, k) => {
      const run = path(frames, k, player)
      return {
        focus: run[run.length - 1] ?? [52.5, 34],
        marks: [{ kind: 'path', pts: run, tone: tone(team), n: 1 }],
        labels: player ? [{ id: player, role: `${fmt(topSpeed(run.slice(-6)), c.lang, 1)} km/h`, tone: tone(team) }] : [],
        items: c.fan ? [
          { n: 1, label: fill(c.s.sceneFan.sprintSpeed, { name: c.maps.names[player] ?? '', v: fmt(topSpeed(run), c.lang, 1) }), value: '' },
          { n: 2, label: fill(c.s.sceneFan.sprintDist, { d: fmt(length(run), c.lang) }), value: '' },
        ] : [
          { n: 1, label: t.speed, value: fill(t.speedV, { v: fmt(topSpeed(run), c.lang, 1) }) },
          { n: 2, label: t.distance, value: fill(t.distanceV, { d: fmt(length(run), c.lang) }) },
        ],
      }
    },
  }
}

/** The scene that explains one insight, measured on whichever frame is showing. */
export function buildScene(match: MatchDetail, packet: Packet, maps: PitchMaps, s: Strings, lang: Lang, fan = false): SceneSpec {
  const spec = pick({ match, packet, maps, s, lang, fan })
  if (!fan) return spec
  const measure = spec.measure
  return { ...spec, measure: (frames, k) => {
    const m = measure(frames, k)
    return { ...m, marks: m.marks.map((mark) => ({ ...mark, n: undefined })) }
  } }
}

function pick(c: Ctx): SceneSpec {
  const { packet } = c
  const type = packet.data.type ?? ''
  if (type === 'decoy_run') return decoy(c)
  if (type === 'chain') return chance(c)
  if (type === 'between_lines_gap') return lines(c)
  if (type === 'overload' || type === 'momentum_swing') return overload(c)
  if (['record', 'standout', 'fatigue'].includes(type) && packet.data.players?.length) return sprint(c)
  if (type === 'pressure_shift' || type === 'counter_press') return press(c, teamIndex(c, packet.data.teams?.[0]))
  return press(c, null)
}

export function sceneWindow(packet: Packet): [number, number] {
  const [start, end] = packet.viz?.window ?? [packet.show_at - 12, packet.show_at]
  const stop = Math.min(end, packet.show_at) + 1.5
  return [Math.max(start - 2, stop - 22), stop]
}
