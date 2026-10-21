import { useEffect, useRef } from 'react'
import type { MatchClock } from '../clock'
import { palette, type Palette } from '../theme'

const L = 105
const W = 68
const M = 3

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

function trailColour(p: Palette, tone: number): string {
  return [p.ink, p.warn, p.good][tone % 3]
}

function drawPitch(ctx: CanvasRenderingContext2D, s: number, p: Palette): void {
  const X = (x: number) => (x + M) * s
  const Y = (y: number) => (W - y + M) * s
  ctx.fillStyle = p.pitch
  ctx.fillRect(X(0), Y(W), L * s, W * s)
  ctx.strokeStyle = p.line
  ctx.lineWidth = Math.max(1, s * 0.12)
  const rect = (x: number, y: number, w: number, h: number) => ctx.strokeRect(X(x), Y(y + h), w * s, h * s)
  rect(0, 0, L, W)
  ctx.beginPath()
  ctx.moveTo(X(L / 2), Y(0))
  ctx.lineTo(X(L / 2), Y(W))
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(X(L / 2), Y(W / 2), 9.15 * s, 0, Math.PI * 2)
  ctx.stroke()
  for (const left of [true, false]) {
    rect(left ? 0 : L - 16.5, W / 2 - 20.16, 16.5, 40.32)
    rect(left ? 0 : L - 5.5, W / 2 - 9.16, 5.5, 18.32)
    rect(left ? -1.6 : L, W / 2 - 3.66, 1.6, 7.32)
    const spot = left ? 11 : L - 11
    ctx.beginPath()
    ctx.arc(X(spot), Y(W / 2), s * 0.3, 0, Math.PI * 2)
    ctx.fillStyle = p.line
    ctx.fill()
    ctx.beginPath()
    const a = Math.acos(5.5 / 9.15)
    if (left) ctx.arc(X(spot), Y(W / 2), 9.15 * s, -a, a)
    else ctx.arc(X(spot), Y(W / 2), 9.15 * s, Math.PI - a, Math.PI + a)
    ctx.stroke()
  }
}

export function Pitch(props: Props) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const latest = useRef(props)
  useEffect(() => {
    latest.current = props
  })

  useEffect(() => {
    let raf = 0
    const render = () => {
      raf = requestAnimationFrame(render)
      const el = canvas.current
      const ctx = el?.getContext('2d')
      if (!el || !ctx) return
      const p = latest.current
      const colours = palette()
      const dpr = window.devicePixelRatio || 1
      const width = el.clientWidth
      const s = width / (L + 2 * M)
      const height = (W + 2 * M) * s
      if (el.width !== Math.round(width * dpr)) {
        el.width = Math.round(width * dpr)
        el.height = Math.round(height * dpr)
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)
      drawPitch(ctx, s, colours)
      const X = (x: number) => (x + M) * s
      const Y = (y: number) => (W - y + M) * s

      for (const trail of p.trails) {
        if (trail.points.length < 2) continue
        const colour = trailColour(colours, trail.tone)
        ctx.strokeStyle = colour
        ctx.lineWidth = s * 0.4
        ctx.lineCap = 'round'
        ctx.setLineDash([s * 1.2, s * 0.8])
        ctx.beginPath()
        trail.points.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))))
        ctx.stroke()
        ctx.setLineDash([])
        const [x1, y1] = trail.points[trail.points.length - 1]
        const [x0, y0] = trail.points[Math.max(0, trail.points.length - 4)]
        const ang = Math.atan2(-(y1 - y0), x1 - x0)
        ctx.fillStyle = colour
        ctx.beginPath()
        ctx.moveTo(X(x1) + Math.cos(ang) * s * 1.4, Y(y1) + Math.sin(ang) * s * 1.4)
        ctx.lineTo(X(x1) + Math.cos(ang + 2.5) * s * 1.1, Y(y1) + Math.sin(ang + 2.5) * s * 1.1)
        ctx.lineTo(X(x1) + Math.cos(ang - 2.5) * s * 1.1, Y(y1) + Math.sin(ang - 2.5) * s * 1.1)
        ctx.fill()
      }

      const state = p.clock.positions(performance.now())
      if (!state) return
      const r = s * 1.15
      for (const [id, [x, y]] of Object.entries(state.players)) {
        const team = p.teamOf[id] ?? 0
        const followed = p.followed.includes(id)
        const lit = p.highlight.includes(id)
        if (followed || lit) {
          ctx.beginPath()
          ctx.arc(X(x), Y(y), r * 1.8, 0, Math.PI * 2)
          ctx.strokeStyle = followed ? colours.ink : colours.warn
          ctx.lineWidth = s * 0.32
          ctx.stroke()
        }
        ctx.beginPath()
        ctx.arc(X(x), Y(y), r, 0, Math.PI * 2)
        ctx.fillStyle = team === 0 ? colours.us : colours.opp
        ctx.fill()
        ctx.fillStyle = colours.dotInk
        ctx.font = `600 ${Math.max(9, r * 1.05)}px "Google Sans", system-ui, sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(String(p.shirts[id] ?? ''), X(x), Y(y) + 0.5)
        if (followed) {
          ctx.font = `600 ${Math.max(10, s * 1.5)}px "Google Sans", system-ui, sans-serif`
          ctx.fillStyle = colours.ink
          ctx.fillText(p.names[id] ?? id, X(x), Y(y) + r * 2.7)
        }
      }
      const [bx, by, bz] = state.ball
      ctx.beginPath()
      ctx.ellipse(X(bx), Y(by), s * 0.55, s * 0.35, 0, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(0,0,0,0.18)'
      ctx.fill()
      ctx.beginPath()
      ctx.arc(X(bx), Y(by) - bz * s * 0.6, s * 0.6, 0, Math.PI * 2)
      ctx.fillStyle = colours.card
      ctx.fill()
      ctx.strokeStyle = colours.ink
      ctx.lineWidth = 1.2
      ctx.stroke()

      ctx.font = `500 ${Math.max(11, s * 1.5)}px "Google Sans", system-ui, sans-serif`
      for (const tag of p.tags) {
        const pos = state.players[tag.player]
        if (!pos) continue
        const tx = X(pos[0])
        const ty = Y(pos[1]) - r * 2.4
        const w = ctx.measureText(tag.text).width + s * 2.4
        const h = s * 2.6
        ctx.fillStyle = colours.card
        ctx.beginPath()
        ctx.roundRect(tx - w / 2, ty - h, w, h, h / 2)
        ctx.fill()
        ctx.strokeStyle = colours.line
        ctx.lineWidth = 1
        ctx.stroke()
        ctx.fillStyle = colours.ink
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(tag.text, tx, ty - h / 2)
      }
    }
    raf = requestAnimationFrame(render)
    return () => cancelAnimationFrame(raf)
  }, [])

  return <canvas ref={canvas} className="pitch" />
}
