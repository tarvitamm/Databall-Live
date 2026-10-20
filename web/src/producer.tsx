import { useEffect, useMemo, useRef, useState } from 'react'
import { api, openSocket, type Stream } from './api'
import { MatchClock } from './clock'
import { ScoreBug } from './components/Broadcast'
import { Pitch } from './components/Pitch'
import { Timeline } from './components/Timeline'
import { clock } from './i18n'
import type { FrameMsg, MatchDetail, StateMsg } from './types'

type Status = 'queued' | 'awaiting_approval' | 'aired' | 'rejected' | 'expired' | 'killed' | 'switched_off'

interface Line {
  headline: string
  body?: string
}

interface Insight {
  id: string
  type: string
  period: number
  t: number
  claim: string
  mechanism: string
  consequence: string
  signals: Record<string, number | number[]>
  confidence: number
  significance: number
  entities: { teams?: string[]; players?: string[] }
  model: { analyst?: string; prompt_version?: string }
  lines: Record<string, Record<string, Line>>
  status: Status
}

interface Control {
  mode: 'auto' | 'supervised'
  killed: boolean
  disabled: string[]
  unreliable: number
}

interface CrewReport {
  executors: Record<string, { calls: number; ms: number }>
  insights: number
  rejections: number
  fallbacks: number
}

interface Note {
  id: number
  executor: string
  note: string
  detail: Record<string, unknown>
}

const TYPES: [string, string][] = [
  ['chain', 'Chances'],
  ['decoy_run', 'Decoy runs'],
  ['pressure_shift', 'Pressing'],
  ['momentum_swing', 'Momentum'],
  ['counter_press', 'Counter-press'],
  ['between_lines_gap', 'Gaps'],
  ['overload', 'Overloads'],
  ['fatigue', 'Fatigue'],
  ['match_state', 'Match state'],
  ['speed_tag', 'Speed tags'],
]

const AGENTS: [string, string][] = [
  ['moment_router', 'Moment router'],
  ['tactical_analyst', 'Tactical analyst'],
  ['player_lens', 'Player lens'],
  ['editor', 'Editor'],
  ['storyteller', 'Storyteller'],
  ['verifier', 'Verifier'],
  ['producer', 'Producer'],
]

const STATUS_LABEL: Record<Status, string> = {
  queued: 'Queued',
  awaiting_approval: 'Needs approval',
  aired: 'On air',
  rejected: 'Rejected',
  expired: 'Expired',
  killed: 'Killed',
  switched_off: 'Switched off',
}

function useConsole(match: MatchDetail | null) {
  const clockRef = useMemo(() => new MatchClock(), [])
  const socket = useRef<Stream | null>(null)
  const [now, setNow] = useState({ period: 1, t: 0 })
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [control, setControl] = useState<Control>({ mode: 'auto', killed: false, disabled: [], unreliable: 0 })
  const [insights, setInsights] = useState<Record<string, Insight>>({})
  const [crew, setCrew] = useState<CrewReport | null>(null)
  const [notes, setNotes] = useState<Note[]>([])
  const [state, setState] = useState<StateMsg | null>(null)

  useEffect(() => {
    if (!match) return
    let second = -1
    let noteId = 0
    const s = openSocket(`/ws/console/${match.id}`, (msg) => {
      const kind = msg.kind as string
      if (kind === 'frame') {
        const f = msg as unknown as FrameMsg
        clockRef.push(f)
        if (Math.floor(f.t) !== second) {
          second = Math.floor(f.t)
          setNow({ period: f.period, t: f.t })
        }
      } else if (kind === 'hello') {
        setPlaying(Boolean(msg.playing))
        setSpeed(Number(msg.speed))
        setControl(msg.control as Control)
        setCrew(msg.crew as CrewReport)
        setNow({ period: Number(msg.period), t: Number(msg.t) })
        const list = msg.insights as Insight[]
        setInsights(Object.fromEntries(list.map((i) => [i.id, i])))
        const saved = (msg.notes as Omit<Note, 'id'>[] | undefined) ?? []
        setNotes(saved.map((n) => ({ ...n, id: (noteId += 1) })))
      } else if (kind === 'insight') {
        const ins = msg as unknown as Insight
        setInsights((all) => ({ ...all, [ins.id]: ins }))
      } else if (kind === 'status') {
        const id = msg.insight as string
        setInsights((all) => (all[id] ? { ...all, [id]: { ...all[id], status: msg.status as Status } } : all))
      } else if (kind === 'crew') {
        setCrew(msg as unknown as CrewReport)
      } else if (kind === 'note') {
        noteId += 1
        const note = { id: noteId, executor: msg.executor as string, note: msg.note as string, detail: msg.detail as Record<string, unknown> }
        setNotes((all) => [note, ...all].slice(0, 30))
      } else if (kind === 'control') {
        setPlaying(Boolean(msg.playing))
        setSpeed(Number(msg.speed))
        setControl(msg.control as Control)
      } else if (kind === 'state') {
        setState(msg as unknown as StateMsg)
      } else if (kind === 'playing') {
        setPlaying(Boolean(msg.playing))
      }
    })
    socket.current = s
    return () => s.close()
  }, [match, clockRef])

  const send = (msg: object) => socket.current?.send(msg)
  return { clock: clockRef, now, playing, speed, control, insights, crew, notes, state, send }
}

function SignalList({ signals }: { signals: Insight['signals'] }) {
  return (
    <dl className="signals">
      {Object.entries(signals).map(([k, v]) => (
        <div key={k}>
          <dt>{k.replace(/_/g, ' ')}</dt>
          <dd>{Array.isArray(v) ? `${v[0]} → ${v[1]}` : v}</dd>
        </div>
      ))}
    </dl>
  )
}

function InsightCard({ ins, names, onApprove, onReject, supervised }: {
  ins: Insight
  names: Record<string, string>
  onApprove: () => void
  onReject: () => void
  supervised: boolean
}) {
  const [open, setOpen] = useState(false)
  const analyst = ins.lines.en?.analyst
  const decided = ['aired', 'rejected', 'expired', 'killed', 'switched_off'].includes(ins.status)
  return (
    <article className={`insight-card status-${ins.status}`}>
      <header>
        <span className="feed-time">{clock(ins.period, ins.t)}</span>
        <span className="type-chip">{ins.type.replace(/_/g, ' ')}</span>
        <span className={`status-chip ${ins.status}`}>{STATUS_LABEL[ins.status] ?? ins.status}</span>
      </header>
      <h4>{ins.claim}</h4>
      {analyst?.body && <p>{analyst.body}</p>}
      <div className="meta">
        <span>confidence {Math.round(ins.confidence * 100)}%</span>
        <span>significance {Math.round(ins.significance * 100)}%</span>
        <span>{ins.model.analyst}</span>
        {ins.entities.players?.length ? <span>{ins.entities.players.map((p) => names[p] ?? p).join(', ')}</span> : null}
      </div>
      {supervised && !decided && (
        <div className="actions">
          <button className="approve" onClick={onApprove}>
            Approve
          </button>
          <button className="reject" onClick={onReject}>
            Reject
          </button>
        </div>
      )}
      <button className="link" onClick={() => setOpen(!open)}>
        {open ? 'Hide details' : 'Signals and languages'}
      </button>
      {open && (
        <div className="details">
          <SignalList signals={ins.signals} />
          {Object.entries(ins.lines).map(([lang, personas]) => (
            <div key={lang} className="lang-block">
              <strong>{lang.toUpperCase()}</strong>
              {Object.entries(personas).map(([persona, line]) => (
                <p key={persona}>
                  <em>{persona.replace('_', ' ')}</em> {line.headline}
                  {line.body ? ` · ${line.body}` : ''}
                </p>
              ))}
            </div>
          ))}
        </div>
      )}
    </article>
  )
}

export function ProducerView({ id }: { id: string }) {
  const [match, setMatch] = useState<MatchDetail | null>(null)
  useEffect(() => {
    api.match(id).then(setMatch)
  }, [id])
  const c = useConsole(match)
  const maps = useMemo(() => {
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
  if (!match) return <main className="loading">Blindside</main>

  const all = Object.values(c.insights).sort((a, b) => b.period - a.period || b.t - a.t)
  const waiting = all.filter((i) => i.status === 'awaiting_approval')
  const rundown = all.filter((i) => i.status !== 'awaiting_approval')
  const supervised = c.control.mode === 'supervised'
  const base = `${location.pathname}?match=${id}&live=1`

  return (
    <main className="producer">
      <header className="topbar">
        <span className="console-title">Producer</span>
        <ScoreBug match={match} now={c.now} state={c.state} />
        <div className="transport">
          <button className="primary" onClick={() => c.send({ action: c.playing ? 'pause' : 'play' })}>
            {c.playing ? 'Pause' : 'Start broadcast'}
          </button>
          <div className="segmented small">
            {[1, 2, 5, 10].map((v) => (
              <button key={v} className={c.speed === v ? 'on' : ''} onClick={() => c.send({ action: 'speed', value: v })}>
                {v}x
              </button>
            ))}
          </div>
          <a className="ghost-link" href={base} target="_blank" rel="noreferrer">
            Fan view
          </a>
          <a className="ghost-link" href={`${base}&view=overlay`} target="_blank" rel="noreferrer">
            Overlay
          </a>
        </div>
        <Timeline match={match} now={c.now} onSeek={(period, t) => c.send({ action: 'seek', period, t })} />
      </header>

      <section className="console-controls">
        <div className="segmented">
          <button className={!supervised ? 'on' : ''} onClick={() => c.send({ action: 'mode', value: 'auto' })}>
            Automatic
          </button>
          <button className={supervised ? 'on' : ''} onClick={() => c.send({ action: 'mode', value: 'supervised' })}>
            Approve before air
          </button>
        </div>
        <button className={`kill ${c.control.killed ? 'on' : ''}`} onClick={() => c.send({ action: 'kill', value: !c.control.killed })}>
          {c.control.killed ? 'Graphics off: restore' : 'Kill all graphics'}
        </button>
        <button
          className={`inject ${c.control.unreliable > 0 ? 'on' : ''}`}
          onClick={() => c.send({ action: 'unreliable', value: c.control.unreliable > 0 ? 0 : 0.3 })}
        >
          {c.control.unreliable > 0 ? `Storyteller errors: on (${Math.round(c.control.unreliable * 100)}%)` : 'Inject storyteller errors'}
        </button>
        <div className="type-toggles">
          {TYPES.map(([type, label]) => {
            const off = c.control.disabled.includes(type)
            return (
              <button key={type} className={off ? 'off' : 'on'} onClick={() => c.send({ action: 'type', value: type, on: off })}>
                {label}
              </button>
            )
          })}
        </div>
      </section>

      <div className="console-grid">
        <section className="panel">
          <h3>Program</h3>
          <Pitch clock={c.clock} {...maps} followed={[]} highlight={[]} tags={[]} trails={[]} />
          <div className="state-foot">
            <span>{c.state?.label ?? 'balanced'}</span>
            <span>
              xG {c.state?.xg[match.home.code]?.toFixed(2) ?? '0.00'} - {c.state?.xg[match.away.code]?.toFixed(2) ?? '0.00'}
            </span>
          </div>
        </section>

        <section className="panel rundown">
          {supervised && (
            <>
              <h3>Needs approval ({waiting.length})</h3>
              {waiting.length === 0 && <p className="muted">Nothing waiting. New insights stop here until you approve them.</p>}
              {waiting.map((ins) => (
                <InsightCard
                  key={ins.id}
                  ins={ins}
                  names={maps.names}
                  supervised
                  onApprove={() => c.send({ action: 'approve', insight: ins.id })}
                  onReject={() => c.send({ action: 'reject', insight: ins.id })}
                />
              ))}
            </>
          )}
          <h3>Rundown</h3>
          {rundown.length === 0 && <p className="muted">Insights from the crew appear here as the match plays.</p>}
          {rundown.map((ins) => (
            <InsightCard
              key={ins.id}
              ins={ins}
              names={maps.names}
              supervised={supervised}
              onApprove={() => c.send({ action: 'approve', insight: ins.id })}
              onReject={() => c.send({ action: 'reject', insight: ins.id })}
            />
          ))}
        </section>

        <section className="panel crew">
          <h3>Insight crew</h3>
          <div className="crew-counters">
            <div>
              <b>{c.crew?.insights ?? 0}</b>
              <span>insights</span>
            </div>
            <div>
              <b>{c.crew?.rejections ?? 0}</b>
              <span>lines rejected</span>
            </div>
            <div>
              <b>{c.crew?.fallbacks ?? 0}</b>
              <span>template fallbacks</span>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th>Calls</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {AGENTS.map(([key, label]) => (
                <tr key={key}>
                  <td>{label}</td>
                  <td>{c.crew?.executors[key]?.calls ?? 0}</td>
                  <td>{(c.crew?.executors[key]?.ms ?? 0).toFixed(1)} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h4>Crew log</h4>
          {c.notes.length === 0 && <p className="muted">No rejections. Turn on storyteller errors to see the verifier at work.</p>}
          <ul className="notes">
            {c.notes.map((n) => (
              <li key={n.id} className={n.note}>
                <strong>{n.note === 'rejected' ? 'Rejected' : n.note === 'fallback' ? 'Template fallback' : 'Dropped repeat'}</strong>
                {n.note === 'rejected' && (
                  <>
                    <span>
                      {String(n.detail.insight)} · {String(n.detail.lang)} · {String(n.detail.persona)} · attempt {String(n.detail.attempt)}
                    </span>
                    <span className="muted">{(n.detail.reasons as string[]).join('; ')}</span>
                    <q>{String(n.detail.body)}</q>
                  </>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </main>
  )
}
