export const L = 105
export const W = 68

export type V3 = [number, number, number]

const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
const norm = (a: V3): V3 => {
  const n = Math.hypot(a[0], a[1], a[2])
  return [a[0] / n, a[1] / n, a[2] / n]
}

export interface Look {
  grassA: string
  grassB: string
  mark: string
  net: string
  post: string
  us: string
  opp: string
  ink: string
  dotInk: string
}

/** A pinhole camera over the pitch: x along the length, y across, z up, in metres. */
export class Camera {
  pos: V3 = [L / 2, -45, 50]
  f: V3 = [0, 1, 0]
  r: V3 = [1, 0, 0]
  u: V3 = [0, 0, 1]
  F = 1
  cx = 0
  cy = 0

  look(pos: V3, target: V3): void {
    this.pos = pos
    this.f = norm(sub(target, pos))
    this.r = norm(cross(this.f, [0, 0, 1]))
    this.u = cross(this.r, this.f)
  }

  depth(x: number, y: number): number {
    return dot(sub([x, y, 0], this.pos), this.f)
  }

  /** Screen x, screen y and pixels per metre at that depth. */
  project(x: number, y: number, z: number): [number, number, number] {
    const d = sub([x, y, z], this.pos)
    const depth = Math.max(dot(d, this.f), 0.1)
    const k = this.F / depth
    return [this.cx + dot(d, this.r) * k, this.cy - dot(d, this.u) * k, k]
  }
}

export function poly(ctx: CanvasRenderingContext2D, cam: Camera, pts: [number, number, number][]): void {
  ctx.beginPath()
  pts.forEach(([x, y, z], i) => {
    const [sx, sy] = cam.project(x, y, z)
    if (i) ctx.lineTo(sx, sy)
    else ctx.moveTo(sx, sy)
  })
}

export function arc(cx: number, cy: number, r: number, a0: number, a1: number, n = 40): [number, number, number][] {
  return Array.from({ length: n + 1 }, (_, i) => {
    const a = a0 + ((a1 - a0) * i) / n
    return [cx + r * Math.cos(a), cy + r * Math.sin(a), 0] as [number, number, number]
  })
}

export function groundEllipse(ctx: CanvasRenderingContext2D, cam: Camera, x: number, y: number, r: number): void {
  poly(ctx, cam, arc(x, y, r, 0, Math.PI * 2, 36))
  ctx.closePath()
}

export function drawSurface(ctx: CanvasRenderingContext2D, cam: Camera, look: Look, stripes = 18, edge = 4): void {
  for (let i = 0; i < stripes; i++) {
    const x0 = (L / stripes) * i - (i === 0 ? edge : 0)
    const x1 = (L / stripes) * (i + 1) + (i === stripes - 1 ? edge : 0)
    ctx.fillStyle = i % 2 ? look.grassA : look.grassB
    poly(ctx, cam, [[x0, -edge, 0], [x1, -edge, 0], [x1, W + 2.5, 0], [x0, W + 2.5, 0]])
    ctx.fill()
  }
}

export function drawLines(ctx: CanvasRenderingContext2D, cam: Camera, look: Look, width: number): void {
  ctx.strokeStyle = look.mark
  ctx.lineWidth = width
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

export function drawGoal(ctx: CanvasRenderingContext2D, cam: Camera, look: Look, left: boolean): void {
  const x = left ? 0 : L
  const back = left ? -2 : L + 2
  const y0 = W / 2 - 3.66
  const y1 = W / 2 + 3.66
  ctx.strokeStyle = look.net
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
  ctx.strokeStyle = look.post
  ctx.lineWidth = Math.max(1.5, cam.project(x, W / 2, 0)[2] * 0.14)
  poly(ctx, cam, [[x, y0, 0], [x, y0, 2.44], [x, y1, 2.44], [x, y1, 0]])
  ctx.stroke()
}

export interface FigureOptions {
  scale?: number
  disc?: boolean
  ring?: string
  number?: string
}

/** A standing player: shadow, optional ground disc and ring, body, head and shirt number. */
export function drawFigure(ctx: CanvasRenderingContext2D, cam: Camera, x: number, y: number, fill: string, look: Look,
  opts: FigureOptions = {}): [number, number] {
  const scale = opts.scale ?? 1
  ctx.fillStyle = 'rgba(0,0,0,0.25)'
  groundEllipse(ctx, cam, x + 0.35 * scale, y + 0.2 * scale, 0.85 * scale)
  ctx.fill()
  if (opts.disc) {
    ctx.fillStyle = fill
    ctx.globalAlpha = 0.85
    groundEllipse(ctx, cam, x, y, 1.0 * scale)
    ctx.fill()
    ctx.globalAlpha = 1
  }
  if (opts.ring) {
    groundEllipse(ctx, cam, x, y, 1.8 * scale)
    ctx.strokeStyle = opts.ring
    ctx.lineWidth = Math.max(1.5, cam.project(x, y, 0)[2] * 0.18 * scale)
    ctx.stroke()
  }
  const [fx, fy, k] = cam.project(x, y, 0.05)
  const [, hy] = cam.project(x, y, 2.4 * scale)
  const w = Math.max(4, k * 0.9 * scale)
  ctx.fillStyle = fill
  ctx.beginPath()
  ctx.roundRect(fx - w / 2, hy, w, fy - hy, [w / 2, w / 2, w / 4, w / 4])
  ctx.fill()
  const shade = ctx.createLinearGradient(fx - w / 2, 0, fx + w / 2, 0)
  shade.addColorStop(0, 'rgba(255,255,255,0.18)')
  shade.addColorStop(1, 'rgba(0,0,0,0.35)')
  ctx.fillStyle = shade
  ctx.fill()
  ctx.beginPath()
  ctx.arc(fx, hy - w * 0.32, w * 0.36, 0, Math.PI * 2)
  ctx.fillStyle = fill
  ctx.fill()
  const font = Math.max(7, k * 0.82 * scale)
  if (opts.number && font >= 8) {
    ctx.fillStyle = look.dotInk
    ctx.font = `600 ${font}px "Google Sans", system-ui, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(opts.number, fx, hy + (fy - hy) * 0.38)
  }
  return [fx, hy - w * 0.9]
}

export function drawBall(ctx: CanvasRenderingContext2D, cam: Camera, x: number, y: number, z: number, scale = 1): void {
  ctx.fillStyle = 'rgba(0,0,0,0.28)'
  groundEllipse(ctx, cam, x, y, 0.32 * scale)
  ctx.fill()
  const [sx, sy, k] = cam.project(x, y, Math.max(z, 0) + 0.22)
  ctx.beginPath()
  ctx.arc(sx, sy, Math.max(2.5, k * 0.4 * scale), 0, Math.PI * 2)
  ctx.fillStyle = '#ffffff'
  ctx.fill()
  ctx.strokeStyle = '#141414'
  ctx.lineWidth = 1
  ctx.stroke()
}
