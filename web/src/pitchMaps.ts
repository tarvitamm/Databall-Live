import { useMemo } from 'react'
import type { MatchDetail } from './types'

export type PitchMaps = ReturnType<typeof usePitchMaps>

export function usePitchMaps(match: MatchDetail | null) {
  return useMemo(() => {
    const teamOf: Record<string, number> = {}
    const shirts: Record<string, number> = {}
    const names: Record<string, string> = {}
    for (const p of match?.players ?? []) {
      teamOf[p.id] = p.team === match?.home.code ? 0 : 1
      shirts[p.id] = p.shirt
      names[p.id] = p.name.split(' ').slice(-1)[0]
    }
    const colours: [[string, string], [string, string]] = [
      match?.home.colours ?? ['#2563eb', '#ffffff'],
      match?.away.colours ?? ['#dc2626', '#ffffff'],
    ]
    return { teamOf, shirts, names, colours }
  }, [match])
}
