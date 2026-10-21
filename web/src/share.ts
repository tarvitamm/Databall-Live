import { api } from './api'
import { clock } from './i18n'
import type { FrameMsg, Lang, MatchDetail, Packet } from './types'

const W = 1080
const H = 1350
const FONT = '"Google Sans", system-ui, sans-serif'
const LIGHT = {
  paper: '#f8f6f2',
  card: '#ffffff',
  ink: '#141414',
  ink2: '#616161',
  ink3: '#8b8781',
  us: '#15694a',
  opp: '#c4552b',
  pitch: '#edf1e7',
  line: '#b3c4ae',
  warn: '#b08400',
}
const BLOBS: [number, number, number, string][] = [
  [0.15, 0.22, 0.6, 'hsla(158, 62%, 28%, 0.95)'],
  [0.58, 0.12, 0.5, 'hsla(146, 55%, 42%, 0.9)'],
  [0.9, 0.35, 0.5, 'hsla(78, 75%, 58%, 0.9)'],
  [0.55, 0.98, 0.6, 'hsla(48, 90%, 72%, 0.95)'],
]

function lines(ctx: CanvasRenderingContext2D, text: string, width: number): string[] {
  const out: string[] = []
  let line = ''
  for (const word of text.split(/\s+/)) {
    const next = line ? `${line} ${word}` : word
    if (ctx.measureText(next).width > width && line) {
      out.push(line)
      line = word
    } else {
      line = next
    }
  }
  if (line) out.push(line)
  return out
}

function drawPitch(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, frame: FrameMsg | null,
  teamOf: Record<string, number>, involved: string[]): void {
  const s = w / 111
  const h = 74 * s
  const X = (v: number) => x + (v + 3) * s
  const Y = (v: number) => y + (71 - v) * s
  ctx.fillStyle = LIGHT.pitch
  ctx.beginPath()
  ctx.roundRect(x, y, w, h, 24)
  ctx.fill()
  ctx.strokeStyle = LIGHT.line
  ctx.lineWidth = 2
  ctx.strokeRect(X(0), Y(68), 105 * s, 68 * s)
  ctx.beginPath()
  ctx.moveTo(X(52.5), Y(0))
  ctx.lineTo(X(52.5), Y(68))
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(X(52.5), Y(34), 9.15 * s, 0, Math.PI * 2)
  ctx.stroke()
  ctx.strokeRect(X(0), Y(54.16), 16.5 * s, 40.32 * s)
  ctx.strokeRect(X(88.5), Y(54.16), 16.5 * s, 40.32 * s)
  if (!frame) return
  for (const [id, [px, py]] of Object.entries(frame.players)) {
    if (involved.includes(id)) {
      ctx.beginPath()
      ctx.arc(X(px), Y(py), s * 2.3, 0, Math.PI * 2)
      ctx.strokeStyle = LIGHT.warn
      ctx.lineWidth = 5
      ctx.stroke()
    }
    ctx.beginPath()
    ctx.arc(X(px), Y(py), s * 1.25, 0, Math.PI * 2)
    ctx.fillStyle = teamOf[id] === 1 ? LIGHT.opp : LIGHT.us
    ctx.fill()
  }
  ctx.beginPath()
  ctx.arc(X(frame.ball[0]), Y(frame.ball[1]), s * 0.8, 0, Math.PI * 2)
  ctx.fillStyle = LIGHT.card
  ctx.fill()
  ctx.strokeStyle = LIGHT.ink
  ctx.lineWidth = 2
  ctx.stroke()
}

export async function shareImage(packet: Packet, match: MatchDetail, teamOf: Record<string, number>,
  footer: string): Promise<Blob> {
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')!
  await document.fonts.ready
  const { frames } = await api.replay(match.id, packet.period, packet.show_at - 1, packet.show_at).catch(() => ({ frames: [] }))
  const frame = frames[frames.length - 1] ?? null

  ctx.fillStyle = '#f1ead0'
  ctx.fillRect(0, 0, W, H)
  ctx.filter = 'blur(70px)'
  for (const [bx, by, r, colour] of BLOBS) {
    const g = ctx.createRadialGradient(bx * W, by * H, 0, bx * W, by * H, r * W)
    g.addColorStop(0, colour)
    g.addColorStop(1, 'rgba(241, 234, 208, 0)')
    ctx.fillStyle = g
    ctx.fillRect(0, 0, W, H)
  }
  ctx.filter = 'none'

  ctx.shadowColor = 'rgba(0,0,0,0.12)'
  ctx.shadowBlur = 50
  ctx.shadowOffsetY = 12
  ctx.fillStyle = LIGHT.card
  ctx.beginPath()
  ctx.roundRect(64, 64, W - 128, H - 128, 48)
  ctx.fill()
  ctx.shadowColor = 'transparent'

  const left = 124
  const width = W - 248
  let y = 168
  ctx.textBaseline = 'alphabetic'
  ctx.fillStyle = LIGHT.ink3
  ctx.font = `500 28px ${FONT}`
  ctx.fillText(`LIVE INSIGHT  ·  ${clock(packet.period, packet.show_at)}`, left, y)
  y += 96
  ctx.fillStyle = LIGHT.ink
  ctx.font = `500 70px ${FONT}`
  for (const line of lines(ctx, packet.text.headline, width).slice(0, 3)) {
    ctx.fillText(line, left, y)
    y += 82
  }
  y += 8
  ctx.fillStyle = LIGHT.ink2
  ctx.font = `400 38px ${FONT}`
  for (const line of lines(ctx, packet.text.body ?? '', width).slice(0, 5)) {
    ctx.fillText(line, left, y)
    y += 54
  }
  const top = Math.max(y + 24, 620)
  const pitchWidth = Math.min(width, ((H - 200 - top) * 111) / 74)
  drawPitch(ctx, left + (width - pitchWidth) / 2, top, pitchWidth, frame, teamOf, packet.data.players ?? [])

  ctx.fillStyle = LIGHT.ink
  ctx.font = `600 34px ${FONT}`
  ctx.fillText('Databall Live', left, H - 136)
  ctx.fillStyle = LIGHT.ink3
  ctx.font = `400 28px ${FONT}`
  ctx.textAlign = 'right'
  ctx.fillText(footer, W - left, H - 136)
  ctx.textAlign = 'left'
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('no image'))), 'image/png'))
}

export function shareLink(match: MatchDetail, lang: Lang): string {
  const url = new URL(location.origin + location.pathname)
  url.searchParams.set('match', match.id)
  url.searchParams.set('view', 'fan')
  url.searchParams.set('lang', lang)
  return url.toString()
}

export function shareText(packet: Packet): string {
  return [packet.text.headline, packet.text.body].filter(Boolean).join('. ')
}

function open(url: string): void {
  window.open(url, '_blank', 'noopener,noreferrer')
}

export function postToX(text: string, link: string): void {
  open(`https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(link)}`)
}

export function postToFacebook(link: string): void {
  open(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(link)}`)
}

export function download(blob: Blob, name = 'databall-live-insight.png'): void {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

export async function postToInstagram(blob: Blob, text: string): Promise<'shared' | 'saved'> {
  const file = new File([blob], 'databall-live-insight.png', { type: 'image/png' })
  if (navigator.canShare?.({ files: [file] })) {
    await navigator.share({ files: [file], text })
    return 'shared'
  }
  download(blob)
  return 'saved'
}
