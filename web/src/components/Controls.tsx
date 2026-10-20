import type { Strings } from '../i18n'
import type { Density, Lang, MatchDetail, Mode, Profile } from '../types'

interface Props {
  match: MatchDetail
  profile: Profile
  speed: number
  s: Strings
  onProfile: (p: Profile) => void
  onSpeed: (v: number) => void
  onCatchUp: () => void
  live?: boolean
}

const MODES: Mode[] = ['fan', 'analyst', 'player_focus']
const LANGS: Lang[] = ['en', 'es', 'et']
const DENSITY: Density[] = ['low', 'medium', 'high']
const SPEEDS = [1, 2, 5, 10]

export function Controls({ match, profile, speed, s, onProfile, onSpeed, onCatchUp, live = false }: Props) {
  const set = (patch: Partial<Profile>) => onProfile({ ...profile, ...patch })
  return (
    <div className="controls">
      <div className="segmented">
        {MODES.map((m) => (
          <button key={m} className={profile.mode === m ? 'on' : ''} onClick={() => set({ mode: m })}>
            {s[m]}
          </button>
        ))}
      </div>
      <select value={profile.clubs[0] ?? ''} onChange={(e) => set({ clubs: e.target.value ? [e.target.value] : [] })} aria-label={s.followClub}>
        <option value="">{s.followClub}</option>
        {[match.home, match.away].map((t) => (
          <option key={t.code} value={t.code}>
            {t.name}
          </option>
        ))}
      </select>
      <select value={profile.players[0] ?? ''} onChange={(e) => set({ players: e.target.value ? [e.target.value] : [] })} aria-label={s.followPlayer}>
        <option value="">{s.followPlayer}</option>
        {[match.home, match.away].map((t) => (
          <optgroup key={t.code} label={t.name}>
            {match.players
              .filter((p) => p.team === t.code)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.shirt} {p.name}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
      <select value={profile.density} onChange={(e) => set({ density: e.target.value as Density })} aria-label={s.density}>
        {DENSITY.map((d) => (
          <option key={d} value={d}>
            {s.density}: {s[d]}
          </option>
        ))}
      </select>
      <div className="segmented small">
        {LANGS.map((l) => (
          <button key={l} className={profile.lang === l ? 'on' : ''} onClick={() => set({ lang: l })}>
            {l.toUpperCase()}
          </button>
        ))}
      </div>
      {!live && (
        <div className="segmented small">
          {SPEEDS.map((v) => (
            <button key={v} className={speed === v ? 'on' : ''} onClick={() => onSpeed(v)}>
              {v}x
            </button>
          ))}
        </div>
      )}
      <button className="primary" onClick={onCatchUp}>
        {s.catchUp}
      </button>
    </div>
  )
}
