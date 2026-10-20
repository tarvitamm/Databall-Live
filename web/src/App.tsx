import { useEffect, useState } from 'react'
import { strings } from './i18n'
import type { Profile } from './types'
import { MatchPicker, MatchView, OverlayView } from './views'

const DEFAULT: Profile = { mode: 'fan', lang: 'en', clubs: [], players: [], density: 'medium' }

function loadProfile(): Profile {
  try {
    const saved = localStorage.getItem('blindside.profile')
    return saved ? { ...DEFAULT, ...(JSON.parse(saved) as Partial<Profile>) } : DEFAULT
  } catch {
    return DEFAULT
  }
}

function fromQuery(base: Profile): Profile {
  const q = new URLSearchParams(location.search)
  const list = (key: string) => (q.get(key) ? q.get(key)!.split(',') : undefined)
  return {
    ...base,
    mode: (q.get('mode') as Profile['mode']) ?? base.mode,
    lang: (q.get('lang') as Profile['lang']) ?? base.lang,
    clubs: list('clubs') ?? base.clubs,
    players: list('players') ?? base.players,
  }
}

export default function App() {
  const query = new URLSearchParams(location.search)
  const [matchId, setMatchId] = useState<string | null>(query.get('match'))
  const [profile, setProfile] = useState<Profile>(() => fromQuery(loadProfile()))

  useEffect(() => {
    try {
      localStorage.setItem('blindside.profile', JSON.stringify(profile))
    } catch {
      return
    }
  }, [profile])

  const open = (id: string | null) => {
    setMatchId(id)
    const url = new URL(location.href)
    if (id) url.searchParams.set('match', id)
    else url.searchParams.delete('match')
    history.pushState(null, '', url)
  }

  if (matchId && query.get('view') === 'overlay') return <OverlayView id={matchId} profile={profile} />
  if (matchId) return <MatchView id={matchId} profile={profile} onProfile={setProfile} onBack={() => open(null)} />
  return <MatchPicker s={strings(profile.lang)} onPick={open} />
}
