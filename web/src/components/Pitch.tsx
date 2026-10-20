import { useEffect, useRef } from 'react'
import type { MatchClock } from '../clock'

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
  colour: string
}

interface Props {
  clock: MatchClock
  teamOf: Record<string, number>
  shirts: Record<string, number>
  names: Record<string, string>
  colours: [[string, string], [string, string]]
  followed: string[]
  highlight: string[]
  tags: Tag[]
  trails: Trail[]
}

function drawPitch(ctx: CanvasRenderingContext2D, s: number): void {
  const X = (x: number) => (x + M) * s
  const Y = (y: number) => (W - y + M) * s
  const stripes = 14
  for (let i = 0; i < stripes; i++) {
    ctx.fillStyle = i % 2 ? '#1d5733' : '#1a5030'
    ctx.fillRect(X((L / stripes) * i), Y(W), (L / stripes) * s + 1, W * s)
  }
  ctx.strokeStyle = 'rgba(255,255,255,0.82)'
  ctx.lineWidth = Math.max(1, s * 0.15)
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
    const x0 = left ? 0 : L - 16.5
    rect(x0, W / 2 - 20.16, 16.5, 40.32)
    rect(left ? 0 : L - 5.5, W / 2 - 9.16, 5.5, 18.32)
    rect(left ? -1.6 : L, W / 2 - 3.66, 1.6, 7.32)
    const spot = left ? 11 : L - 11
    ctx.beginPath()
    ctx.arc(X(spot), Y(W / 2), s * 0.3, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(255,255,255,0.82)'
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
      const el = canvas.current
      if (!el) return
      const p = latest.current
      const dpr = window.devicePixelRatio || 1
      const width = el.clientWidth
      const s = width / (L + 2 * M)
      const height = (W + 2 * M) * s
      if (el.width !== Math.round(width * dpr)) {
        el.width = Math.round(width * dpr)
        el.height = Math.round(height * dpr)
      }
      const ctx = el.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.fillStyle = '#163f27'
      ctx.fillRect(0, 0, width, height)
      drawPitch(ctx, s)
      const X = (x: number) => (x + M) * s
      const Y = (y: number) => (W - y + M) * s

      for (const trail of p.trails) {
        if (trail.points.length < 2) continue
        ctx.strokeStyle = trail.colour
        ctx.lineWidth = s * 0.45
        ctx.lineCap = 'round'
        ctx.setLineDash([s * 1.2, s * 0.8])
        ctx.beginPath()
        trail.points.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))))
        ctx.stroke()
        ctx.setLineDash([])
        const [x1, y1] = trail.points[trail.points.length - 1]
        const [x0, y0] = trail.points[Math.max(0, trail.points.length - 4)]
        const ang = Math.atan2(-(y1 - y0), x1 - x0)
        ctx.fillStyle = trail.colour
        ctx.beginPath()
        ctx.moveTo(X(x1) + Math.cos(ang) * s * 1.4, Y(y1) + Math.sin(ang) * s * 1.4)
        ctx.lineTo(X(x1) + Math.cos(ang + 2.5) * s * 1.1, Y(y1) + Math.sin(ang + 2.5) * s * 1.1)
        ctx.lineTo(X(x1) + Math.cos(ang - 2.5) * s * 1.1, Y(y1) + Math.sin(ang - 2.5) * s * 1.1)
        ctx.fill()
      }

      const state = p.clock.positions(performance.now())
      if (state) {
        const r = s * 1.15
        for (const [id, [x, y]] of Object.entries(state.players)) {
          const team = p.teamOf[id] ?? 0
          const [fill, ink] = p.colours[team]
          const followed = p.followed.includes(id)
          const lit = p.highlight.includes(id)
          if (followed || lit) {
            ctx.beginPath()
            ctx.arc(X(x), Y(y), r * 1.75, 0, Math.PI * 2)
            ctx.strokeStyle = followed ? '#3ddc97' : '#ffd166'
            ctx.lineWidth = s * 0.35
            ctx.stroke()
          }
          ctx.beginPath()
          ctx.arc(X(x), Y(y), r, 0, Math.PI * 2)
          ctx.fillStyle = fill
          ctx.fill()
          ctx.lineWidth = s * 0.18
          ctx.strokeStyle = ink
          ctx.stroke()
          ctx.fillStyle = ink
          ctx.font = `600 ${Math.max(9, r * 1.05)}px Inter, sans-serif`
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText(String(p.shirts[id] ?? ''), X(x), Y(y) + 0.5)
          if (followed) {
            ctx.font = `600 ${Math.max(10, s * 1.5)}px Inter, sans-serif`
            ctx.fillStyle = '#ffffff'
            ctx.fillText(p.names[id] ?? id, X(x), Y(y) + r * 2.6)
          }
        }
        const [bx, by, bz] = state.ball
        ctx.beginPath()
        ctx.ellipse(X(bx), Y(by), s * 0.55, s * 0.35, 0, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(0,0,0,0.35)'
        ctx.fill()
        ctx.beginPath()
        ctx.arc(X(bx), Y(by) - bz * s * 0.6, s * 0.55, 0, Math.PI * 2)
        ctx.fillStyle = '#ffffff'
        ctx.fill()
        ctx.strokeStyle = '#111'
        ctx.lineWidth = 1
        ctx.stroke()

        ctx.font = `600 ${Math.max(11, s * 1.6)}px Inter, sans-serif`
        for (const tag of p.tags) {
          const pos = state.players[tag.player]
          if (!pos) continue
          const tx = X(pos[0])
          const ty = Y(pos[1]) - r * 2.4
          const w = ctx.measureText(tag.text).width + s * 2
          const h = s * 2.6
          ctx.fillStyle = 'rgba(10,16,32,0.88)'
          ctx.beginPath()
          ctx.roundRect(tx - w / 2, ty - h, w, h, h / 2)
          ctx.fill()
          ctx.strokeStyle = '#3ddc97'
          ctx.lineWidth = 1.5
          ctx.stroke()
          ctx.fillStyle = '#ffffff'
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText(tag.text, tx, ty - h / 2)
        }
      }
      raf = requestAnimationFrame(render)
    }
    raf = requestAnimationFrame(render)
    return () => cancelAnimationFrame(raf)
  }, [])

  return <canvas ref={canvas} className="pitch" />
}
