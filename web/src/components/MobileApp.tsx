import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../api'
import { clock, stateLabel, type Strings } from '../i18n'
import type { PitchMaps } from '../pitchMaps'
import type { CatchUp, Lang, MatchDetail, Metric, Packet, PlayerStats } from '../types'
import { isOpen, type Broadcast } from '../useBroadcast'
import { useLive } from '../useLive'
import { badgeFor } from '../badges'
import { Badge, CallsList, LeaguePanel, PredictionPopup, ResultPopup, ScoreChip } from './Engage'
import { FantasyPanel } from './Fantasy'
import { EventMaps, LiveText } from './MatchCentre'
import { CloseIcon, Mark, ReplayIcon, ShareIcon } from './Icons'
import { ShareSheet } from './Moments'
import { Pitch } from './Pitch'
import { Scene } from './Scene'

const POPUP_MS = 8000

interface AppProps {
  match: MatchDetail
  b: Broadcast
  maps: PitchMaps
  s: Strings
  lang: Lang
}

function useTick(ms: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(id)
  }, [ms])
  return now
}

function side(match: MatchDetail, p: Packet): string {
  const team = p.data.teams?.[0]
  return team === match.home.code ? 'us' : team === match.away.code ? 'opp' : ''
}

function scoreLine(match: MatchDetail, b: Broadcast): string {
  const score = b.state?.score ?? {}
  return `${match.home.name} ${score[match.home.code] ?? 0}-${score[match.away.code] ?? 0} ${match.away.name}`
}

function Hero({ match, b, s }: { match: MatchDetail; b: Broadcast; s: Strings }) {
  const score = b.state?.score ?? {}
  const [home, away] = b.state?.control ?? [50, 50]
  const share = home + away > 0 ? (home / (home + away)) * 100 : 50
  return (
    <header className="app-hero">
      <div className="app-top">
        <span className="app-brand">
          <Mark />
          Databall Live
        </span>
        <span className="hero-right">
          <ScoreChip b={b} s={s} />
          <span className="live-pill">{s.live}</span>
        </span>
      </div>
      <div className="app-score">
        <b className="us">{match.home.name}</b>
        <div className="nums">
          {score[match.home.code] ?? 0}
          <i>-</i>
          {score[match.away.code] ?? 0}
          <small>{clock(b.now.period, b.now.t)}</small>
        </div>
        <b className="opp">{match.away.name}</b>
      </div>
      <div className="app-control">
        <span>{s.control}</span>
        <div className="split">
          <i className="us" style={{ width: `${share}%` }} />
          <i className="opp" style={{ width: `${100 - share}%` }} />
        </div>
        <span>{stateLabel(b.state?.label ?? 'balanced', s)}</span>
      </div>
    </header>
  )
}

interface CardProps {
  p: Packet
  match: MatchDetail
  maps: PitchMaps
  s: Strings
  lang: Lang
  open: boolean
  onReplay: () => void
  onShare: () => void
}

function FeedCard({ p, match, maps, s, lang, open, onReplay, onShare }: CardProps) {
  const replayable = Boolean(p.viz && p.viz.kind !== 'none')
  return (
    <article className={`app-card ${side(match, p)}`}>
      <div className="app-card-head">
        <span className="time">{clock(p.period, p.show_at)}</span>
        <span className="kind">{s.kind[p.data.type ?? ''] ?? ''}</span>
        <Badge p={p} s={s} />
      </div>
      <h4>{p.text.headline}</h4>
      {p.text.body && <p>{p.text.body}</p>}
      {open && <Scene match={match} packet={p} maps={maps} s={s} lang={lang} compact />}
      <div className="app-actions">
        {replayable && (
          <button onClick={onReplay}>
            <ReplayIcon />
            {open ? s.hideReplay : s.replay}
          </button>
        )}
        <button onClick={onShare}>
          <ShareIcon />
          {s.repost}
        </button>
      </div>
    </article>
  )
}

function Popup({ p, match, s, onReplay, onShare, onClose }: Omit<CardProps, 'open' | 'maps' | 'lang'> & { onClose: () => void }) {
  return (
    <div className={`popup ${side(match, p)} ${badgeFor(p, s)?.tone ?? ''}`} role="status">
      <div className="popup-head">
        <span className="dot" />
        {badgeFor(p, s)?.label ?? s.newInsight} · {clock(p.period, p.show_at)}
        <button className="icon" onClick={onClose} aria-label={s.close}>
          <CloseIcon />
        </button>
      </div>
      <b>{p.text.headline}</b>
      {p.text.body && <p>{p.text.body}</p>}
      <div className="app-actions">
        {p.viz && p.viz.kind !== 'none' ? (
          <button onClick={onReplay}>
            <ReplayIcon />
            {s.replay}
          </button>
        ) : null}
        <button onClick={onShare}>
          <ShareIcon />
          {s.repost}
        </button>
      </div>
    </div>
  )
}

function Phone({ path, children }: { path: string; children: ReactNode }) {
  return (
    <div className="phone">
      <div className="phone-top">
        <span className="phone-url">live.databall.eu/{path}</span>
      </div>
      <div className="phone-screen">{children}</div>
    </div>
  )
}

function MobileApp({ match, b, maps, s, lang, path, top, body }: AppProps & { path: string; top: ReactNode; body?: ReactNode }) {
  const now = useTick(500)
  const [open, setOpen] = useState<string | null>(null)
  const [sharing, setSharing] = useState<Packet | null>(null)
  const [dismissed, setDismissed] = useState<Set<string>>(() => new Set())
  const hide = (id: string) => setDismissed((all) => new Set(all).add(id))
  const latest = b.recap ?? b.feed[0]
  const insight = latest && !dismissed.has(latest.packet) && now - (latest.received ?? 0) < POPUP_MS ? latest : null
  const settled = b.calls.find((c) => c.result && b.picks[c.prompt.id] && now - (c.settledAt ?? 0) < POPUP_MS && !dismissed.has(`r${c.prompt.id}`))
  const asking = b.calls.find((c) => isOpen(c, b.now) && !dismissed.has(`p${c.prompt.id}`) && (!b.picks[c.prompt.id] || now - c.received < 2500))
  const replay = (p: Packet) => {
    setOpen(p.packet)
    hide(p.packet)
  }
  const share = (p: Packet) => {
    setSharing(p)
    hide(p.packet)
  }
  let popup: ReactNode = null
  if (settled) {
    popup = <ResultPopup key={`r${settled.prompt.id}`} call={settled} b={b} s={s} lang={lang} onClose={() => hide(`r${settled.prompt.id}`)} />
  } else if (insight && (!asking || (insight.received ?? 0) > asking.received)) {
    popup = (
      <Popup key={insight.packet} p={insight} match={match} s={s} onReplay={() => replay(insight)} onShare={() => share(insight)} onClose={() => hide(insight.packet)} />
    )
  } else if (asking) {
    popup = <PredictionPopup key={`p${asking.prompt.id}`} call={asking} b={b} s={s} lang={lang} onClose={() => hide(`p${asking.prompt.id}`)} />
  }
  return (
    <Phone path={path}>
      <Hero match={match} b={b} s={s} />
      <div className="app-body">
        {top}
        {body ?? (
          <>
            <CallsList b={b} s={s} lang={lang} />
            <h5 className="app-section">{s.yourFeed}</h5>
            {b.feed.length === 0 && !b.recap && <p className="app-empty">{s.noInsights}</p>}
          </>
        )}
        {!body && [...(b.recap ? [b.recap] : []), ...b.feed].map((p) => (
          <FeedCard
            key={p.packet}
            p={p}
            match={match}
            maps={maps}
            s={s}
            lang={lang}
            open={open === p.packet}
            onReplay={() => setOpen(open === p.packet ? null : p.packet)}
            onShare={() => share(p)}
          />
        ))}
      </div>
      {popup}
      {sharing && (
        <ShareSheet packet={sharing} match={match} maps={maps} lang={lang} footer={scoreLine(match, b)} s={s} onClose={() => setSharing(null)} />
      )}
    </Phone>
  )
}

function CatchUpSheet({ match, b, lang, s, onClose }: { match: MatchDetail; b: Broadcast; lang: Lang; s: Strings; onClose: () => void }) {
  const [data, setData] = useState<CatchUp | null>(null)
  const { period, t } = b.now
  useEffect(() => {
    api.catchUp(match.id, period, t, lang).then(setData)
  }, [match.id, period, t, lang])
  return (
    <div className="catchup">
      <div className="sheet-head">
        <b>{s.catchUp}</b>
        <button className="icon" onClick={onClose} aria-label={s.close}>
          <CloseIcon />
        </button>
      </div>
      {data && (
        <>
          <p className="muted">
            {s.xg} {data.xg[match.home.code]?.toFixed(2)} - {data.xg[match.away.code]?.toFixed(2)} · {stateLabel(data.state.label, s)}
          </p>
          <ol className="moments">
            {data.moments.map((m, i) => (
              <li key={i}>
                <strong>{m.headline}</strong>
                {m.body && <p>{m.body}</p>}
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}

const METRICS: Metric[] = ['', 'speed', 'offball', 'pressing', 'chances', 'passing']

function MetricTracker({ match, b, s, maps, lang, metric }: AppProps & { metric: Metric }) {
  const data = useLive(match, b.now)
  if (!metric || !data) return null
  const t = s.live2
  const num = (v: number, d = 0) => (lang === 'en' ? v.toFixed(d) : v.toFixed(d).replace('.', ','))
  const home = data.teams[match.home.code]
  const away = data.teams[match.away.code]
  const lead = data.leaders
  const name = (pid: string | null | undefined) => (pid ? (maps.names[pid] ?? pid) : '-')
  const team: [string, string, number, number][] = []
  const people: [string, string][] = []
  if (metric === 'speed') {
    people.push([t.sprint, `${name(lead.sprint.player)} · ${num(lead.sprint.kmh, 1)} km/h`])
    people.push([t.distance, `${name(lead.distance.player)} · ${num(lead.distance.km, 2)} km`])
    if (lead.shot) people.push([t.fastShot, `${name(lead.shot.player)} · ${lead.shot.kmh} km/h`])
  } else if (metric === 'offball') {
    team.push([t.decoys, 'decoy_runs', home.decoy_runs, away.decoy_runs], [t.runs, 'runs', home.runs, away.runs])
  } else if (metric === 'pressing') {
    team.push([t.pressures, 'pressures', home.pressures, away.pressures])
  } else if (metric === 'chances') {
    team.push([t.shots, 'shots', home.shots, away.shots], [t.xg, 'xg', home.xg, away.xg])
    if (lead.shot) people.push([t.fastShot, `${name(lead.shot.player)} · ${lead.shot.kmh} km/h`])
  } else {
    team.push([t.passAcc, 'pass_accuracy', home.pass_accuracy, away.pass_accuracy], [t.hard, 'hard_completed', home.hard_completed, away.hard_completed])
    if (lead.pass) people.push([t.hardest, `${name(lead.pass.player)} → ${name(lead.pass.recipient)} · ${num(lead.pass.difficulty, 1)} ${t.of10}`])
  }
  return (
    <section className="tracker">
      <div className="tracker-head">
        <span className="dot" />
        {s.metricName[metric]}
      </div>
      {team.map(([label, key, h, a]) => (
        <div key={key} className="tracker-row">
          <span className="tracker-label">{label}</span>
          <div className="tracker-vs">
            <b className="us">{key === 'xg' ? num(h, 2) : h}{key === 'pass_accuracy' ? '%' : ''}</b>
            <div className="split">
              <i className="us" style={{ width: `${(h / Math.max(h + a, 0.001)) * 100}%` }} />
              <i className="opp" style={{ width: `${(a / Math.max(h + a, 0.001)) * 100}%` }} />
            </div>
            <b className="opp">{key === 'xg' ? num(a, 2) : a}{key === 'pass_accuracy' ? '%' : ''}</b>
          </div>
        </div>
      ))}
      {people.map(([label, value]) => (
        <div key={label} className="tracker-row person">
          <span className="tracker-label">{label}</span>
          <b>{value}</b>
        </div>
      ))}
    </section>
  )
}

export function FanApp({ club, onClub, metric, onMetric, ...props }: AppProps & {
  club: string
  onClub: (code: string) => void
  metric: Metric
  onMetric: (m: Metric) => void
}) {
  const { match, b, s } = props
  const [catchUp, setCatchUp] = useState(false)
  const [tab, setTab] = useState<'feed' | 'match' | 'fantasy' | 'league'>('feed')
  const ticker = b.tags[0]?.text ?? b.cards[0]?.text.headline
  const tabs = (
    <div className="app-tabs" role="tablist">
      {(['feed', 'match', 'fantasy', 'league'] as const).map((k) => (
        <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>
          {s.tabs[k]}
        </button>
      ))}
    </div>
  )
  if (tab === 'match')
    return (
      <MobileApp
        {...props}
        path={`match/${match.id}`}
        top={tabs}
        body={
          <>
            <EventMaps match={match} now={b.now} maps={props.maps} s={s} lang={props.lang} />
            <LiveText match={match} now={b.now} feed={b.feed} s={s} lang={props.lang} />
          </>
        }
      />
    )
  if (tab === 'fantasy') return <MobileApp {...props} path={`fantasy/${match.id}`} top={tabs} body={<FantasyPanel match={match} now={b.now} maps={props.maps} s={s} />} />
  if (tab === 'league') return <MobileApp {...props} path={`predict/${match.id}`} top={tabs} body={<LeaguePanel match={match} b={b} s={s} lang={props.lang} />} />
  const top = (
    <>
      {tabs}
      <div className="app-chips">
        {['', match.home.code, match.away.code].map((code) => (
          <button key={code || 'all'} className={club === code ? 'on' : ''} onClick={() => onClub(code)}>
            {code === match.home.code ? match.home.name : code === match.away.code ? match.away.name : s.bothClubs}
          </button>
        ))}
      </div>
      <div className="app-chips metric-chips">
        <span>{s.yourMetric}</span>
        {METRICS.map((m) => (
          <button key={m || 'all'} className={metric === m ? 'on' : ''} onClick={() => onMetric(m)}>
            {s.metricName[m]}
          </button>
        ))}
      </div>
      <MetricTracker {...props} metric={metric} />
      {ticker && (
        <div className="app-ticker">
          <span className="dot" />
          {ticker}
        </div>
      )}
      {catchUp ? (
        <CatchUpSheet match={match} b={b} lang={props.lang} s={s} onClose={() => setCatchUp(false)} />
      ) : (
        <button className="app-catchup" onClick={() => setCatchUp(true)}>
          {s.catchUp}
        </button>
      )}
    </>
  )
  return <MobileApp {...props} path={`live/${match.id}`} top={top} />
}

function usePlayerStats(match: MatchDetail, pid: string, now: { period: number; t: number }) {
  const [stats, setStats] = useState<PlayerStats | null>(null)
  const t = Math.floor(now.t / 10) * 10
  useEffect(() => {
    let live = true
    api.player(match.id, pid, now.period, t).then((x) => live && setStats(x)).catch(() => {})
    return () => {
      live = false
    }
  }, [match.id, pid, now.period, t])
  return stats?.id === pid ? stats : null
}

export function PlayerApp({ player, onPlayer, ...props }: AppProps & { player: string; onPlayer: (pid: string) => void }) {
  const { match, b, s } = props
  const stats = usePlayerStats(match, player, b.now)
  const info = match.players.find((p) => p.id === player)
  const runs = stats ? Object.values(stats.runs).reduce((x, y) => x + y, 0) : 0
  const top = (
    <section className="player-card">
      <select value={player} onChange={(e) => onPlayer(e.target.value)} aria-label={s.followPlayer}>
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
      {info && (
        <div className={`player-head ${info.team === match.home.code ? 'us' : 'opp'}`}>
          <span className="shirt">{info.shirt}</span>
          <div>
            <b>{info.name}</b>
            <small>
              {info.position} · {info.team === match.home.code ? match.home.name : match.away.name}
            </small>
          </div>
        </div>
      )}
      <div className="player-cam">
        <Pitch clock={b.clock} {...props.maps} followed={[player]} highlight={[]} tags={[]} trails={[]} zoom={player} />
        <span className="cam-chip">
          <i />
          {s.playerCam}
        </span>
      </div>
      {stats && (
        <>
          <div className="player-strip">
            <div>
              <b>{stats.distance_km}</b>
              <span>km</span>
            </div>
            <div>
              <b>{stats.sprints}</b>
              <span>{s.sprints}</span>
            </div>
            <div>
              <b>{stats.top_speed_kmh}</b>
              <span>km/h</span>
            </div>
          </div>
          {stats.season && (
            <>
              <h5 className="app-section">
                {s.today} · {s.thisSeason} ({stats.season.games} {s.games})
              </h5>
              <table className="season-table">
                <tbody>
                  {([
                    ['distance_km', s.distance, stats.distance_km],
                    ['sprints', s.sprints, stats.sprints],
                    ['top_speed_kmh', s.topSpeed, stats.top_speed_kmh],
                    ['decoy_runs', s.decoys, stats.decoy_runs],
                    ['pressures', s.pressures, stats.pressures],
                  ] as [string, string, number][]).map(([key, label, today]) => (
                    <tr key={key}>
                      <td>{label}</td>
                      <td className="num today">{today}</td>
                      <td className="num">
                        {stats.season!.avg[key]?.toFixed(1)} <small>{s.seasonAvg}</small>
                      </td>
                      <td className="num">
                        {stats.season!.best[key]} <small>{s.seasonBest}</small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="season-chips">
                <span>
                  <em>{stats.season.totals.decoy_runs + stats.decoy_runs}</em> {s.decoys} · #{stats.season.rank.decoy_runs[0]} {s.inLeague}
                </span>
                <span>
                  <em>{stats.season.totals.goals}</em> {s.goals}
                </span>
              </div>
            </>
          )}
          <dl className="player-stats">
            <div>
              <dt>{s.runs}</dt>
              <dd>{runs}</dd>
            </div>
            <div>
              <dt>{s.decoys}</dt>
              <dd>{stats.decoy_runs}</dd>
            </div>
            <div>
              <dt>{s.dragged}</dt>
              <dd>{stats.defenders_dragged_m} m</dd>
            </div>
            <div>
              <dt>{s.pressures}</dt>
              <dd>{stats.pressures}</dd>
            </div>
            <div>
              <dt>{s.passes}</dt>
              <dd>
                {stats.passes_complete}/{stats.passes}
              </dd>
            </div>
            <div>
              <dt>{s.shots}</dt>
              <dd>{stats.shots}</dd>
            </div>
          </dl>
          <h5 className="app-section">{s.theirMoments}</h5>
          {stats.patterns.length === 0 && <p className="app-empty">{s.noMoments}</p>}
          <div className="moment-chips">
            {stats.patterns
              .slice(-8)
              .reverse()
              .map((m) => (
                <span key={m.id}>
                  <em>{clock(m.period, m.t)}</em>
                  {s.pattern[m.type] ?? m.type.replace(/_/g, ' ')}
                </span>
              ))}
          </div>
        </>
      )}
    </section>
  )
  return <MobileApp {...props} path={`player/${player}`} top={top} />
}
