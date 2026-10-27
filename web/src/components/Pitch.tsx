import { useEffect, useRef } from 'react'
import type { MatchClock } from '../clock'
import { Camera, drawBall, drawFigure, drawGoal, drawLines, drawSurface, L, poly, W, type Look } from '../render3d'
import { palette, type Palette } from '../theme'

const ASPECT = 9 / 16
const MAX_PAN = 9
const CAMERA: [number, number, number] = [L / 2, -45, 50]
const ZOOM_HALF = 15

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
  showNames?: boolean
  zoom?: string
}

function fit(cam: Camera, width: number, height: number): void {
  cam.look(CAMERA, [L / 2, 32, 0])
  cam.F = 1
  cam.cx = 0
  cam.cy = 0
  const [left] = cam.project(0, 0, 0)
  const [right] = cam.project(L, 0, 0)
  const [, top] = cam.project(L / 2, W + 3, 2)
  const [, bottom] = cam.project(L / 2, -3, 0)
  cam.F = Math.min((width * 1.1) / (right - left), (height * 0.86) / (bottom - top))
  cam.cx = width / 2 - (cam.F * (left + right)) / 2
  cam.cy = height * 0.985 - cam.F * bottom
}

function close(cam: Camera, at: [number, number], width: number, height: number): void {
  cam.look([at[0] - 5, at[1] - 30, 20], [at[0], at[1] + 2, 0])
  cam.F = 1
  cam.cx = 0
  cam.cy = 0
  const [l] = cam.project(at[0] - ZOOM_HALF, at[1], 0)
  const [r] = cam.project(at[0] + ZOOM_HALF, at[1], 0)
  cam.F = width / (r - l)
  const [fx, fy] = cam.project(at[0], at[1], 0)
  cam.cx = width / 2 - fx
  cam.cy = height * 0.62 - fy
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
  const pattern = ctx.createPattern(crowdTexture(), 'repeat')
  if (pattern) {
    ctx.fillStyle = pattern
    ctx.fillRect(0, farY * 0.18, width, farY * 0.82)
  }
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
    let focus: [number, number] | null = null
    const cam = new Camera()
    const render = () => {
      raf = requestAnimationFrame(render)
      const el = canvas.current
      const ctx = el?.getContext('2d')
      if (!el || !ctx) return
      const p = latest.current
      const colours = palette()
      const look: Look = colours
      const dpr = window.devicePixelRatio || 1
      const width = el.clientWidth
      const height = width * ASPECT
      if (`${width}x${height}x${dpr}` !== size) {
        size = `${width}x${height}x${dpr}`
        el.width = Math.round(width * dpr)
        el.height = Math.round(height * dpr)
        fit(cam, width, height)
      }
      const state = p.clock.positions(performance.now())
      const spot = p.zoom ? state?.players[p.zoom] : undefined
      if (spot) {
        focus = focus ? [focus[0] + (spot[0] - focus[0]) * 0.06, focus[1] + (spot[1] - focus[1]) * 0.06] : spot
        close(cam, focus, width, height)
      } else {
        if (focus) fit(cam, width, height)
        focus = null
        const target = state ? Math.max(-MAX_PAN, Math.min(MAX_PAN, (state.ball[0] - L / 2) * 0.22)) : 0
        pan += (target - pan) * 0.03
        cam.look(CAMERA, [L / 2 + pan, 32, 0])
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      drawStadium(ctx, cam, colours, width, height)
      drawBoards(ctx, cam, colours)
      drawSurface(ctx, cam, look)
      drawLines(ctx, cam, look, spot ? 1.2 : Math.max(1, cam.F / 900))
      drawGoal(ctx, cam, look, true)
      drawGoal(ctx, cam, look, false)

      for (const trail of p.trails) {
        if (trail.points.length < 2) continue
        const k = cam.project(L / 2, W / 2, 0)[2]
        ctx.strokeStyle = [colours.ink, colours.warn, colours.good][trail.tone % 3]
        ctx.lineWidth = k * 0.35
        ctx.lineCap = 'round'
        ctx.setLineDash([k * 1.1, k * 0.8])
        poly(ctx, cam, trail.points.map(([x, y]) => [x, y, 0.02]))
        ctx.stroke()
        ctx.setLineDash([])
      }

      if (!state) return
      const [bx, by, bz] = state.ball
      const ballDepth = cam.depth(bx, by)
      let ballDrawn = false
      const people = Object.entries(state.players)
        .map(([id, [x, y]]) => ({ id, x, y, depth: cam.depth(x, y) }))
        .sort((a, b) => b.depth - a.depth)
      for (const man of people) {
        if (!ballDrawn && ballDepth > man.depth) {
          drawBall(ctx, cam, bx, by, bz)
          ballDrawn = true
        }
        const followed = p.followed.includes(man.id)
        const lit = p.highlight.includes(man.id)
        const fill = (p.teamOf[man.id] ?? 0) === 0 ? colours.us : colours.opp
        const [hx, hy] = drawFigure(ctx, cam, man.x, man.y, fill, look, {
          ring: followed ? colours.ink : lit ? colours.warn : undefined,
          number: String(p.shirts[man.id] ?? ''),
        })
        if (followed || p.showNames) {
          const k = cam.project(man.x, man.y, 0)[2]
          ctx.font = `600 ${Math.min(16, Math.max(10, k * (followed ? 0.9 : 0.7)))}px "Google Sans", system-ui, sans-serif`
          ctx.fillStyle = followed ? colours.ink : 'rgba(255,255,255,0.92)'
          ctx.textAlign = 'center'
          ctx.textBaseline = 'alphabetic'
          ctx.fillText(p.names[man.id] ?? man.id, hx, hy)
        }
      }
      if (!ballDrawn) drawBall(ctx, cam, bx, by, bz)

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
