import type { FrameMsg } from './types'

export class MatchClock {
  prev: FrameMsg | null = null
  cur: FrameMsg | null = null
  prevAt = 0
  curAt = 0

  push(frame: FrameMsg): void {
    this.prev = this.cur
    this.prevAt = this.curAt
    this.cur = frame
    this.curAt = performance.now()
  }

  positions(now: number): { players: Record<string, [number, number]>; ball: [number, number, number] } | null {
    const cur = this.cur
    if (!cur) return null
    const prev = this.prev
    if (!prev || prev.period !== cur.period) return { players: cur.players, ball: cur.ball }
    const span = Math.max(this.curAt - this.prevAt, 16)
    const a = Math.min(Math.max((now - this.curAt) / span, 0), 1)
    const lerp = (p: number, c: number) => p + (c - p) * a
    const players: Record<string, [number, number]> = {}
    for (const [id, c] of Object.entries(cur.players)) {
      const p = prev.players[id] ?? c
      players[id] = [lerp(p[0], c[0]), lerp(p[1], c[1])]
    }
    const ball: [number, number, number] = [
      lerp(prev.ball[0], cur.ball[0]),
      lerp(prev.ball[1], cur.ball[1]),
      lerp(prev.ball[2], cur.ball[2]),
    ]
    return { players, ball }
  }
}
