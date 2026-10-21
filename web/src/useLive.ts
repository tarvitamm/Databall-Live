import { useEffect, useState } from 'react'
import { api } from './api'
import type { LiveNumbers, MatchDetail } from './types'

export function useLive(match: MatchDetail, now: { period: number; t: number }, every = 20): LiveNumbers | null {
  const [data, setData] = useState<LiveNumbers | null>(null)
  const t = Math.floor(now.t / every) * every
  useEffect(() => {
    let live = true
    api.live(match.id, now.period, t).then((x) => live && setData(x)).catch(() => {})
    return () => {
      live = false
    }
  }, [match.id, now.period, t])
  return data
}
