import { useEffect, useState } from 'react'

export type Theme = 'light' | 'dark'

export interface Palette {
  grassA: string
  grassB: string
  mark: string
  net: string
  post: string
  standTop: string
  standBottom: string
  boardMid: string
  us: string
  opp: string
  ink: string
  ink3: string
  dotInk: string
  warn: string
  good: string
  card: string
}

function initial(): Theme {
  try {
    const saved = localStorage.getItem('databall.theme')
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    return 'light'
  }
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(initial)
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('databall.theme', theme)
    } catch {
      return
    }
  }, [theme])
  return { theme, toggle: () => setTheme((t) => (t === 'light' ? 'dark' : 'light')) }
}

let cached: Palette | null = null
let cachedFor = ''

export function palette(): Palette {
  const key = document.documentElement.dataset.theme ?? ''
  if (cached && key === cachedFor) return cached
  const css = getComputedStyle(document.documentElement)
  const v = (name: string) => css.getPropertyValue(name).trim()
  cached = {
    grassA: v('--grass-a'),
    grassB: v('--grass-b'),
    mark: v('--mark'),
    net: v('--net'),
    post: v('--post'),
    standTop: v('--stand-top'),
    standBottom: v('--stand-bottom'),
    boardMid: v('--board-mid'),
    us: v('--us'),
    opp: v('--opp'),
    ink: v('--ink'),
    ink3: v('--ink-3'),
    dotInk: v('--dot-ink'),
    warn: v('--warn'),
    good: v('--good'),
    card: v('--card'),
  }
  cachedFor = key
  return cached
}
