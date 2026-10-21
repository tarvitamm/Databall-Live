import type { Strings } from './i18n'
import type { Packet } from './types'

export function badgeFor(p: Packet, s: Strings): { label: string; tone: string } | null {
  const key = p.data.key ?? ''
  if (key.startsWith('goal')) return { label: s.badge.goal, tone: 'goal' }
  if (key === 'record_speed_league') return { label: s.badge.league, tone: 'gold' }
  if (key === 'record_speed_recent') return { label: s.badge.recent, tone: 'gold' }
  if (key.startsWith('record')) return { label: s.badge.record, tone: 'gold' }
  if (p.data.type === 'standout') return { label: s.badge.standout, tone: 'gold' }
  if (key.startsWith('preview')) return { label: s.badge.preview, tone: 'ink' }
  if (key.endsWith('_season')) return { label: s.badge.season, tone: 'soft' }
  if (p.data.type === 'recap') return { label: p.text.headline, tone: 'ink' }
  return null
}
