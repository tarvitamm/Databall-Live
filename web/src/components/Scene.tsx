import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { clock, type Strings } from '../i18n'
import type { PitchMaps } from '../pitchMaps'
import { Camera, drawBall, drawFigure, drawGoal, drawLines, drawSurface, groundEllipse, poly, type Look } from '../render3d'
import { buildScene, sceneWindow, type SceneMark, type Tone } from '../scene'
import type { FrameMsg, Lang, MatchDetail, Packet } from '../types'
import { CloseIcon, PauseIcon, PlayIcon } from './Icons'

const LOOK: Look = {
  grassA: '#0f1c25',
  grassB: '#0c1820',
  mark: 'rgba(255,255,255,0.17)',
  net: 'rgba(255,255,255,0.22)',
  post: 'rgba(255,255,255,0.75)',
  us: '#b4e443',
  opp: '#f0a272',
  ink: '#eef3f1',
  dotInk: '#101a21',
}
const TONES: Record<Tone, string> = { us: LOOK.us, opp: LOOK.opp, ink: '#eef3f1', warn: '#e8ce72' }
const RATE = 5

type P2 = [number, number]

function badge(ctx: CanvasRenderingContext2D, x: number, y: number, n: number): void {
  ctx.beginPath()
  ctx.arc(x, y, 10, 0, Math.PI * 2)
  ctx.fillStyle = '#ffffff'
  ctx.fill()
  ctx.strokeStyle = '#0a121a'
  ctx.lineWidth = 2
  ctx.stroke()
  ctx.fillStyle = '#0a121a'
  ctx.font = '700 11px "Google Sans", system-ui, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(String(n), x, y + 0.5)
}

function drawMark(ctx: CanvasRenderingContext2D, cam: Camera, m: SceneMark): [number, number] | null {
  const colour = TONES[m.tone]
  const k = cam.project(52.5, 34, 0)[2]
  ctx.strokeStyle = colour
  ctx.lineWidth = Math.max(2, k * 0.22)
  ctx.lineCap = 'round'
  ctx.setLineDash(m.dashed ? [k * 1.4, k * 0.9] : [])
  if (m.kind === 'circle') {
    groundEllipse(ctx, cam, m.at[0], m.at[1], m.r)
    ctx.fillStyle = colour
    ctx.globalAlpha = 0.1
    ctx.fill()
    ctx.globalAlpha = 1
    ctx.stroke()
    ctx.setLineDash([])
    const [x, y] = cam.project(m.at[0], m.at[1] + m.r, 0)
    return [x, y]
  }
  const pts: P2[] = m.kind === 'line' ? [m.a, m.b] : m.pts
  if (pts.length < 2) {
    ctx.setLineDash([])
    return null
  }
  poly(ctx, cam, pts.map(([x, y]) => [x, y, 0.05]))
  ctx.stroke()
  ctx.setLineDash([])
  if (m.kind === 'line' && m.arrow) {
    const [bx, by] = cam.project(m.b[0], m.b[1], 0.05)
    const [ax, ay] = cam.project(m.a[0] + (m.b[0] - m.a[0]) * 0.9, m.a[1] + (m.b[1] - m.a[1]) * 0.9, 0.05)
    const ang = Math.atan2(by - ay, bx - ax)
    const size = Math.max(8, k * 1.1)
    ctx.fillStyle = colour
    ctx.beginPath()
    ctx.moveTo(bx, by)
    ctx.lineTo(bx - size * Math.cos(ang - 0.45), by - size * Math.sin(ang - 0.45))
    ctx.lineTo(bx - size * Math.cos(ang + 0.45), by - size * Math.sin(ang + 0.45))
    ctx.fill()
  }
  const mid = pts[Math.floor(pts.length / 2)]
  const [x, y] = cam.project(mid[0], mid[1], 0.05)
  return [x, y]
}

interface Props {
  match: MatchDetail
  packet: Packet
  maps: PitchMaps
  s: Strings
  lang: Lang
  compact?: boolean
  onClose?: () => void
}

export function Scene({ match, packet, maps, s, lang, compact = false, onClose }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [frames, setFrames] = useState<FrameMsg[]>([])
  const [k, setK] = useState(0)
  const [playing, setPlaying] = useState(true)
  const spec = useMemo(() => buildScene(match, packet, maps, s, lang, compact), [match, packet, maps, s, lang, compact])
  const live = useRef({ pos: 0, playing: true, frames: [] as FrameMsg[], spec })
  const [start, end] = sceneWindow(packet)

  useEffect(() => {
    live.current.spec = spec
  }, [spec])

  useEffect(() => {
    live.current.playing = playing
  }, [playing])

  useEffect(() => {
    let alive = true
    api.replay(match.id, packet.period, start, end).then((r) => {
      if (!alive) return
      live.current.frames = r.frames
      live.current.pos = 0
      setFrames(r.frames)
    })
    return () => {
      alive = false
    }
  }, [match.id, packet.period, start, end])

  useEffect(() => {
    let raf = 0
    let last = performance.now()
    let shown = -1
    let focus: P2 | null = null
    const cam = new Camera()
    const render = (now: number) => {
      raf = requestAnimationFrame(render)
      const st = live.current
      const el = canvas.current
      const ctx = el?.getContext('2d')
      const dt = Math.min((now - last) / 1000, 0.1)
      last = now
      if (!el || !ctx || st.frames.length < 2) return
      const n = st.frames.length
      if (st.playing) {
        st.pos += dt * RATE * (compact ? 1 : 0.6)
        if (st.pos >= n - 1) {
          if (compact) st.pos = 0
          else {
            st.pos = n - 1
            setPlaying(false)
          }
        }
      }
      const i = Math.min(Math.floor(st.pos), n - 1)
      const a = st.pos - i
      if (i !== shown) {
        shown = i
        setK(i)
      }
      const f0 = st.frames[i]
      const f1 = st.frames[Math.min(i + 1, n - 1)]
      const players: Record<string, P2> = {}
      for (const [id, p0] of Object.entries(f0.players)) {
        const p1 = f1.players[id] ?? p0
        players[id] = [p0[0] + (p1[0] - p0[0]) * a, p0[1] + (p1[1] - p0[1]) * a]
      }
      const ball = f0.ball.map((v, j) => v + (f1.ball[j] - v) * a) as [number, number, number]
      // measure on the in-between frame too, so marks glide with the players instead of jumping 5 times a second
      const m = st.spec.measure([...st.frames.slice(0, i + 1), { ...f0, players, ball }], i + 1)

      const dpr = window.devicePixelRatio || 1
      const width = el.clientWidth
      const height = el.clientHeight
      if (el.width !== Math.round(width * dpr) || el.height !== Math.round(height * dpr)) {
        el.width = Math.round(width * dpr)
        el.height = Math.round(height * dpr)
      }
      focus = focus ? [focus[0] + (m.focus[0] - focus[0]) * 0.05, focus[1] + (m.focus[1] - focus[1]) * 0.05] : m.focus
      cam.look([focus[0] - 8, focus[1] - 38, 26], [focus[0], focus[1] + 3, 0])
      cam.F = 1
      cam.cx = 0
      cam.cy = 0
      const half = compact ? 22 : 26
      const [l] = cam.project(focus[0] - half, focus[1], 0)
      const [r] = cam.project(focus[0] + half, focus[1], 0)
      cam.F = (width / (r - l)) * (compact ? 0.95 : 0.85)
      const [fx, fy] = cam.project(focus[0], focus[1], 0)
      cam.cx = width * (compact ? 0.5 : 0.62) - fx
      cam.cy = height * 0.56 - fy

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const bg = ctx.createLinearGradient(0, 0, 0, height)
      bg.addColorStop(0, '#070d13')
      bg.addColorStop(1, '#0d1821')
      ctx.fillStyle = bg
      ctx.fillRect(0, 0, width, height)
      drawSurface(ctx, cam, LOOK, 18, 30)
      drawLines(ctx, cam, LOOK, 1.2)
      drawGoal(ctx, cam, LOOK, true)
      drawGoal(ctx, cam, LOOK, false)

      const badges: [number, number, number][] = []
      for (const mark of m.marks) {
        const at = drawMark(ctx, cam, mark)
        if (at && mark.n) badges.push([at[0], at[1], mark.n])
      }

      const key = new Set([...st.spec.players, ...m.labels.map((x) => x.id)])
      const heads: Record<string, [number, number]> = {}
      const order = Object.entries(players).sort((p, q) => cam.depth(q[1][0], q[1][1]) - cam.depth(p[1][0], p[1][1]))
      for (const [id, [x, y]] of order) {
        const fill = (maps.teamOf[id] ?? 0) === 0 ? LOOK.us : LOOK.opp
        heads[id] = drawFigure(ctx, cam, x, y, fill, LOOK, {
          disc: key.has(id),
          ring: m.labels.some((lab) => lab.id === id) ? '#ffffff' : undefined,
          number: String(maps.shirts[id] ?? ''),
        })
      }
      drawBall(ctx, cam, ball[0], ball[1], ball[2])
      for (const [x, y, num] of badges) badge(ctx, x, y, num)

      const big = compact ? 11.5 : 13
      const h = compact ? 19 : 22
      const placed: [number, number, number, number][] = []
      for (const lab of m.labels) {
        const head = heads[lab.id]
        if (!head) continue
        const name = maps.names[lab.id] ?? lab.id
        ctx.font = `600 ${big}px "Google Sans", system-ui, sans-serif`
        const wName = ctx.measureText(name).width
        ctx.font = `400 ${big - 1}px "Google Sans", system-ui, sans-serif`
        const wRole = ctx.measureText(lab.role).width
        const w = wName + wRole + 20
        const x0 = head[0] - w / 2
        let y0 = head[1] - h - 8
        for (let tries = 0; tries < 5 && placed.some(([x, y, pw]) => x0 < x + pw && x < x0 + w && y0 < y + h && y < y0 + h); tries++) {
          y0 -= h + 4
        }
        placed.push([x0, y0, w, h])
        ctx.fillStyle = 'rgba(10,18,26,0.9)'
        ctx.beginPath()
        ctx.roundRect(x0, y0, w, h, 6)
        ctx.fill()
        ctx.textAlign = 'left'
        ctx.textBaseline = 'middle'
        ctx.font = `600 ${big}px "Google Sans", system-ui, sans-serif`
        ctx.fillStyle = TONES[lab.tone]
        ctx.fillText(name, x0 + 7, y0 + h / 2 + 0.5)
        ctx.font = `400 ${big - 1}px "Google Sans", system-ui, sans-serif`
        ctx.fillStyle = 'rgba(238,243,241,0.75)'
        ctx.fillText(lab.role, x0 + 13 + wName, y0 + h / 2 + 0.5)
      }
    }
    raf = requestAnimationFrame(render)
    return () => cancelAnimationFrame(raf)
  }, [compact, maps])

  const measure = frames.length > 1 ? spec.measure(frames, Math.min(k, frames.length - 1)) : null
  const toggle = () => {
    if (!playing && live.current.pos >= frames.length - 1) live.current.pos = 0
    setPlaying(!playing)
  }
  const scrub = (value: number) => {
    live.current.pos = value
    setK(value)
    setPlaying(false)
  }
  const steps = measure?.items ?? []
  const progress = frames.length > 1 ? k / (frames.length - 1) : 0
  const reveal = compact ? Math.min(steps.length, 1 + Math.floor(progress * steps.length)) : steps.length
  const items = (
    <ol className="scene-items">
      {steps.map((it, i) => (
        <li key={it.n} className={i < reveal ? 'on' : 'off'}>
          <b>{it.n}</b>
          <div>
            <strong>{it.label}</strong>
            {it.value && <span>{it.value}</span>}
          </div>
        </li>
      ))}
    </ol>
  )
  return (
    <div className={`scene ${compact ? 'compact' : ''}`}>
      <div className="scene-stage">
        <canvas ref={canvas} />
        {!compact && (
          <aside className="scene-panel">
            <h3 className={spec.tone}>{spec.title}</h3>
            <p className="scene-sub">{spec.subtitle}</p>
            <p className="scene-measured">{s.scene.measured}</p>
            {items}
          </aside>
        )}
        {onClose && (
          <button className="icon scene-close" onClick={onClose} aria-label={s.close}>
            <CloseIcon />
          </button>
        )}
        <div className="scene-scrub">
          <button onClick={toggle} aria-label={playing ? s.pause : s.play}>
            {playing ? <PauseIcon /> : <PlayIcon />}
          </button>
          <span>{clock(packet.period, start)}</span>
          <input type="range" min={0} max={Math.max(frames.length - 1, 0)} value={k} onChange={(e) => scrub(Number(e.target.value))} aria-label={s.replay} />
          <span>{clock(packet.period, end)}</span>
        </div>
      </div>
      {compact && items}
    </div>
  )
}

export function SceneModal(props: Omit<Props, 'compact'> & { onClose: () => void }) {
  return (
    <div className="scene-modal" onClick={props.onClose}>
      <div className="scene-modal-card" onClick={(e) => e.stopPropagation()}>
        <Scene {...props} />
      </div>
    </div>
  )
}
