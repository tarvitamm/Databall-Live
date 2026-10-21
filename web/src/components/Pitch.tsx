import { useEffect, useRef } from 'react'
import type { MatchClock } from '../clock'
import { palette, type Palette } from '../theme'

const L = 105
const W = 68
const STRIPES = 18
const ASPECT = 9 / 16
const MAX_PAN = 9

export interface Tag {
  id: string
  player: string
  text: string
}

export interface Trail {
  player: string
  points: [number, number][]
  tone: number
}

interface Props {
  clock: MatchClock
  teamOf: Record<string, number>
  shirts: Record<string, number>
  names: Record<string, string>
  followed: string[]
  highlight: string[]
  tags: Tag[]
  trails: Trail[]
}

type V3 = [number, number, number]

const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
const norm = (a: V3): V3 => {
  const n = Math.hypot(a[0], a[1], a[2])
  return [a[0] / n, a[1] / n, a[2] / n]
}

/** A broadcast camera high in the main stand at the halfway line, panning gently with play. */
class Camera {
  pos: V3 = [L / 2, -45, 50]
  f: V3 = [0, 1, 0]
  r: V3 = [1, 0, 0]
  u: V3 = [0, 0, 1]
  F = 1
  cx = 0
  cy = 0

  aim(pan: number): void {
    this.f = norm(sub([L / 2 + pan, 32, 0], this.pos))
    this.r = norm(cross(this.f, [0, 0, 1]))
    this.u = cross(this.r, this.f)
  }

  fit(width: number, height: number): void {
    this.aim(0)
    this.F = 1
    this.cx = 0
    this.cy = 0
    const [left] = this.project(0, 0, 0)
    const [right] = this.project(L, 0, 0)
    const [, top] = this.project(L / 2, W + 3, 2)
    const [, bottom] = this.project(L / 2, -3, 0)
    this.F = Math.min((width * 1.1) / (right - left), (height * 0.86) / (bottom - top))
    this.cx = width / 2 - (this.F * (left + right)) / 2
    this.cy = height * 0.985 - this.F * bottom
  }

  /** Screen x, screen y and pixels per metre at that depth. */
  project(x: number, y: number, z: number): [number, number, number] {
    const d = sub([x, y, z], this.pos)
    const depth = Math.max(dot(d, this.f), 0.1)
    const k = this.F / depth
    return [this.cx + dot(d, this.r) * k, this.cy - dot(d, this.u) * k, k]
  }
}

function poly(ctx: CanvasRenderingContext2D, cam: Camera, pts: [number, number, number][]): void {
  ctx.beginPath()
  pts.forEach(([x, y, z], i) => {
    const [sx, sy] = cam.project(x, y, z)
    if (i) ctx.lineTo(sx, sy)
    else ctx.moveTo(sx, sy)
  })
}

function arc(cx: number, cy: number, r: number, a0: number, a1: number, n = 40): [number, number, number][] {
  return Array.from({ length: n + 1 }, (_, i) => {
    const a = a0 + ((a1 - a0) * i) / n
    return [cx + r * Math.cos(a), cy + r * Math.sin(a), 0] as [number, number, number]
  })
}

let crowd: HTMLCanvasElement | null = null

function crowdTexture(): HTMLCanvasElement {
  if (crowd) return crowd
  crowd = document.createElement('canvas')
  crowd.width = 512
  crowd.height = 128
  const c = crowd.getContext('2d')!
  for (let i = 0; i < 2600; i++) {
    const shade = 120 + Math.floor(Math.random() * 120)
    c.fillStyle = `rgba(${shade},${shade},${shade + 10},${0.06 + Math.random() * 0.12})`
    c.fillRect(Math.random() * 512, Math.random() * 128, 2, 2)
  }
  return crowd
}

function drawStadium(ctx: CanvasRenderingContext2D, cam: Camera, p: Palette, width: number, height: number): void {
  const [, farY] = cam.project(L / 2, W + 3, 0)
  const sky = ctx.createLinearGradient(0, 0, 0, farY)
  sky.addColorStop(0, p.standTop)
  sky.addColorStop(1, p.standBottom)
  ctx.fillStyle = sky
  ctx.fillRect(0, 0, width, height)
  ctx.save()
  ctx.globalAlpha = 0.9
  const pattern = ctx.createPattern(crowdTexture(), 'repeat')
  if (pattern) {
    ctx.fillStyle = pattern
    ctx.fillRect(0, farY * 0.18, width, farY * 0.82)
  }
  ctx.restore()
  const glow = ctx.createRadialGradient(width / 2, -height * 0.2, 0, width / 2, -height * 0.2, width * 0.7)
  glow.addColorStop(0, 'rgba(255,255,255,0.18)')
  glow.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = glow
  ctx.fillRect(0, 0, width, farY)
}

function drawBoards(ctx: CanvasRenderingContext2D, cam: Camera, p: Palette): void {
  const y = W + 2.5
  const [ax, ay] = cam.project(-4, y, 0)
  const [bx, by] = cam.project(L + 4, y, 0)
  const grad = ctx.createLinearGradient(ax, ay, bx, by)
  grad.addColorStop(0, p.us)
  grad.addColorStop(0.5, p.boardMid)
  grad.addColorStop(1, p.opp)
  ctx.fillStyle = grad
  poly(ctx, cam, [[-4, y, 0], [L + 4, y, 0], [L + 4, y, 0.9], [-4, y, 0.9]])
  ctx.fill()
  ctx.fillStyle = 'rgba(255,255,255,0.92)'
  for (let x = 6; x < L; x += 21) {
    const [sx, sy, k] = cam.project(x + 5, y, 0.45)
    ctx.font = `600 ${Math.max(6, k * 0.62)}px "Google Sans", system-ui, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('DATABALL LIVE', sx, sy)
  }
}

function drawPitch(ctx: CanvasRenderingContext2D, cam: Camera, p: Palette): void {
  for (let i = 0; i < STRIPES; i++) {
    const x0 = (L / STRIPES) * i
    const x1 = x0 + L / STRIPES
    ctx.fillStyle = i % 2 ? p.grassA : p.grassB
    poly(ctx, cam, [[x0 - (i === 0 ? 4 : 0), -4, 0], [x1 + (i === STRIPES - 1 ? 4 : 0), -4, 0], [x1 + (i === STRIPES - 1 ? 4 : 0), W + 2.5, 0], [x0 - (i === 0 ? 4 : 0), W + 2.5, 0]])
    ctx.fill()
  }
  ctx.strokeStyle = p.mark
  ctx.lineWidth = Math.max(1, cam.F / 900)
  ctx.lineJoin = 'round'
  const rect = (x: number, y: number, w: number, h: number) => {
    poly(ctx, cam, [[x, y, 0], [x + w, y, 0], [x + w, y + h, 0], [x, y + h, 0], [x, y, 0]])
    ctx.stroke()
  }
  rect(0, 0, L, W)
  poly(ctx, cam, [[L / 2, 0, 0], [L / 2, W, 0]])
  ctx.stroke()
  poly(ctx, cam, arc(L / 2, W / 2, 9.15, 0, Math.PI * 2, 60))
  ctx.stroke()
  for (const left of [true, false]) {
    rect(left ? 0 : L - 16.5, W / 2 - 20.16, 16.5, 40.32)
    rect(left ? 0 : L - 5.5, W / 2 - 9.16, 5.5, 18.32)
    const spot = left ? 11 : L - 11
    const a = Math.acos(5.5 / 9.15)
    poly(ctx, cam, left ? arc(spot, W / 2, 9.15, -a, a) : arc(spot, W / 2, 9.15, Math.PI - a, Math.PI + a))
    ctx.stroke()
  }
}

function drawGoal(ctx: CanvasRenderingContext2D, cam: Camera, p: Palette, left: boolean): void {
  const x = left ? 0 : L
  const back = left ? -2 : L + 2
  const y0 = W / 2 - 3.66
  const y1 = W / 2 + 3.66
  ctx.strokeStyle = p.net
  ctx.lineWidth = 1
  for (const [a, b] of [
    [[back, y0, 0], [back, y0, 2.44]],
    [[back, y1, 0], [back, y1, 2.44]],
    [[back, y0, 2.44], [back, y1, 2.44]],
    [[x, y0, 2.44], [back, y0, 2.44]],
    [[x, y1, 2.44], [back, y1, 2.44]],
  ] as [V3, V3][]) {
    poly(ctx, cam, [a, b])
    ctx.stroke()
  }
  ctx.strokeStyle = p.post
  ctx.lineWidth = Math.max(1.5, cam.project(x, W / 2, 0)[2] * 0.14)
  poly(ctx, cam, [[x, y0, 0], [x, y0, 2.44], [x, y1, 2.44], [x, y1, 0]])
  ctx.stroke()
}

function ellipse(ctx: CanvasRenderingContext2D, cam: Camera, x: number, y: number, r: number): void {
  const [sx, sy, k] = cam.project(x, y, 0)
  const [, near] = cam.project(x, y - r, 0)
  const [, far] = cam.project(x, y + r, 0)
  ctx.beginPath()
  ctx.ellipse(sx, sy, k * r, Math.max(1, Math.abs(near - far) / 2), 0, 0, Math.PI * 2)
}

export function Pitch(props: Props) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const latest = useRef(props)
  useEffect(() => {
    latest.current = props
  })

  useEffect(() => {
    let raf = 0
    let pan = 0
    let size = ''
    const cam = new Camera()
    const render = () => {
      raf = requestAnimationFrame(render)
      const el = canvas.current
      const ctx = el?.getContext('2d')
      if (!el || !ctx) return
      const p = latest.current
      const colours = palette()
      const dpr = window.devicePixelRatio || 1
      const width = el.clientWidth
      const height = width * ASPECT
      if (`${width}x${height}x${dpr}` !== size) {
        size = `${width}x${height}x${dpr}`
        el.width = Math.round(width * dpr)
        el.height = Math.round(height * dpr)
        cam.fit(width, height)
      }
      const state = p.clock.positions(performance.now())
      const target = state ? Math.max(-MAX_PAN, Math.min(MAX_PAN, (state.ball[0] - L / 2) * 0.22)) : 0
      pan += (target - pan) * 0.03
      cam.aim(pan)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      drawStadium(ctx, cam, colours, width, height)
      drawBoards(ctx, cam, colours)
      drawPitch(ctx, cam, colours)
      drawGoal(ctx, cam, colours, true)
      drawGoal(ctx, cam, colours, false)

      for (const trail of p.trails) {
        if (trail.points.length < 2) continue
        const colour = [colours.ink, colours.warn, colours.good][trail.tone % 3]
        const k = cam.project(L / 2, W / 2, 0)[2]
        ctx.strokeStyle = colour
        ctx.lineWidth = k * 0.35
        ctx.lineCap = 'round'
        ctx.setLineDash([k * 1.1, k * 0.8])
        poly(ctx, cam, trail.points.map(([x, y]) => [x, y, 0.02]))
        ctx.stroke()
        ctx.setLineDash([])
      }

      if (!state) return
      const people = Object.entries(state.players)
        .map(([id, [x, y]]) => ({ id, x, y, depth: dot(sub([x, y, 0], cam.pos), cam.f) }))
        .sort((a, b) => b.depth - a.depth)
      const [bx, by, bz] = state.ball
      const ballDepth = dot(sub([bx, by, 0], cam.pos), cam.f)
      let ballDrawn = false
      const drawBall = () => {
        ctx.fillStyle = 'rgba(0,0,0,0.28)'
        ellipse(ctx, cam, bx, by, 0.32)
        ctx.fill()
        const [sx, sy, k] = cam.project(bx, by, Math.max(bz, 0) + 0.22)
        ctx.beginPath()
        ctx.arc(sx, sy, Math.max(2.5, k * 0.4), 0, Math.PI * 2)
        ctx.fillStyle = '#ffffff'
        ctx.fill()
        ctx.strokeStyle = '#141414'
        ctx.lineWidth = 1
        ctx.stroke()
        ballDrawn = true
      }
      for (const man of people) {
        if (!ballDrawn && ballDepth > man.depth) drawBall()
        const team = p.teamOf[man.id] ?? 0
        const fill = team === 0 ? colours.us : colours.opp
        const followed = p.followed.includes(man.id)
        const lit = p.highlight.includes(man.id)
        ctx.fillStyle = 'rgba(0,0,0,0.22)'
        ellipse(ctx, cam, man.x + 0.35, man.y + 0.2, 0.85)
        ctx.fill()
        if (followed || lit) {
          ellipse(ctx, cam, man.x, man.y, 1.8)
          ctx.strokeStyle = followed ? colours.ink : colours.warn
          ctx.lineWidth = Math.max(1.5, cam.project(man.x, man.y, 0)[2] * 0.18)
          ctx.stroke()
        }
        const [fx, fy, k] = cam.project(man.x, man.y, 0.05)
        const [, hy] = cam.project(man.x, man.y, 2.4)
        const w = Math.max(4, k * 0.9)
        const body = ctx.createLinearGradient(fx - w / 2, 0, fx + w / 2, 0)
        body.addColorStop(0, fill)
        body.addColorStop(1, '#000000')
        ctx.fillStyle = fill
        ctx.beginPath()
        ctx.roundRect(fx - w / 2, hy, w, fy - hy, [w / 2, w / 2, w / 4, w / 4])
        ctx.fill()
        ctx.fillStyle = body
        ctx.globalAlpha = 0.35
        ctx.fill()
        ctx.globalAlpha = 1
        ctx.beginPath()
        ctx.arc(fx, hy - w * 0.32, w * 0.36, 0, Math.PI * 2)
        ctx.fillStyle = fill
        ctx.fill()
        const font = Math.max(7, k * 0.82)
        if (font >= 8) {
          ctx.fillStyle = colours.dotInk
          ctx.font = `600 ${font}px "Google Sans", system-ui, sans-serif`
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText(String(p.shirts[man.id] ?? ''), fx, hy + (fy - hy) * 0.38)
        }
        if (followed) {
          ctx.font = `600 ${Math.max(11, k * 0.9)}px "Google Sans", system-ui, sans-serif`
          ctx.fillStyle = colours.ink
          ctx.textAlign = 'center'
          ctx.fillText(p.names[man.id] ?? man.id, fx, hy - w * 1.2)
        }
      }
      if (!ballDrawn) drawBall()

      for (const tag of p.tags) {
        const pos = state.players[tag.player]
        if (!pos) continue
        const [tx, ty, k] = cam.project(pos[0], pos[1], 3.4)
        ctx.font = `500 ${Math.max(11, k * 0.8)}px "Google Sans", system-ui, sans-serif`
        const w = ctx.measureText(tag.text).width + 16
        const h = Math.max(20, k * 1.3)
        ctx.fillStyle = colours.card
        ctx.beginPath()
        ctx.roundRect(tx - w / 2, ty - h, w, h, h / 2)
        ctx.fill()
        ctx.fillStyle = colours.ink
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(tag.text, tx, ty - h / 2)
      }

      const vignette = ctx.createRadialGradient(width / 2, height * 0.55, height * 0.35, width / 2, height * 0.55, width * 0.75)
      vignette.addColorStop(0, 'rgba(0,0,0,0)')
      vignette.addColorStop(1, 'rgba(0,0,0,0.28)')
      ctx.fillStyle = vignette
      ctx.fillRect(0, 0, width, height)
    }
    raf = requestAnimationFrame(render)
    return () => cancelAnimationFrame(raf)
  }, [])

  return <canvas ref={canvas} className="pitch" />
}
