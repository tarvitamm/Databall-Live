import { useEffect, useRef, useState } from 'react'
import { openSocket, type Stream } from './api'
import { Cards, LowerThird, RecapPanel } from './components/Broadcast'
import { Pitch } from './components/Pitch'
import { clock, type Strings } from './i18n'
import type { PitchMaps } from './pitchMaps'
import type { MatchDetail } from './types'
import type { Broadcast } from './useBroadcast'

type Status = 'queued' | 'awaiting_approval' | 'aired' | 'rejected' | 'expired' | 'killed' | 'switched_off'

interface Line {
  headline: string
  body?: string
  source?: string
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
  model: { analyst?: string; storyteller?: string; prompt_version?: string }
  tools: string[]
  lines: Record<string, Record<string, Line>>
  status: Status
}

interface Control {
  mode: 'auto' | 'supervised'
  killed: boolean
  disabled: string[]
  unreliable: number
  model: boolean
}

interface Usage {
  calls: number
  cached: number
  failures: number
  timeouts: number
  input_tokens: number
  output_tokens: number
  mean_s: number
  cost_usd: number
}

interface CrewReport {
  executors: Record<string, { calls: number; ms: number }>
  insights: number
  rejections: number
  fallbacks: number
  model: (Usage & { model: string; agents: Record<string, Usage> }) | null
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

const AGENTS: [string, string, boolean][] = [
  ['moment_router', 'Moment router', false],
  ['tactical_analyst', 'Tactical analyst', true],
  ['player_lens', 'Player lens', true],
  ['editor', 'Editor', false],
  ['storyteller', 'Storyteller', true],
  ['verifier', 'Verifier', false],
  ['recapper', 'Recapper', true],
  ['producer', 'Producer', false],
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

const OFF: Control = { mode: 'auto', killed: false, disabled: [], unreliable: 0, model: false }

function useConsole(match: MatchDetail, room: string) {
  const socket = useRef<Stream | null>(null)
  const [control, setControl] = useState<Control>(OFF)
  const [insights, setInsights] = useState<Record<string, Insight>>({})
  const [crew, setCrew] = useState<CrewReport | null>(null)
  const [notes, setNotes] = useState<Note[]>([])

  useEffect(() => {
    let noteId = 0
    const s = openSocket<Record<string, unknown>>(`/ws/console/${match.id}`, { room }, (msg) => {
      const kind = msg.kind as string
      if (kind === 'hello') {
        setControl(msg.control as Control)
        setCrew(msg.crew as CrewReport)
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
        setControl(msg.control as Control)
      }
    })
    socket.current = s
    return () => s.close()
  }, [match.id, room])

  const send = (msg: object) => socket.current?.send(msg)
  return { control, insights, crew, notes, send }
}

function sourceLabel(source: string | undefined, model: string): string {
  if (source === 'model') return model
  if (source === 'cached') return `${model}, cached`
  if (source === 'fallback') return 'template fallback'
  return 'template'
}

function byModel(source: string | undefined): boolean {
  return source === 'model' || source === 'cached'
}

function InsightCard({ ins, names, onApprove, onReject, supervised, model }: {
  ins: Insight
  names: Record<string, string>
  onApprove: () => void
  onReject: () => void
  supervised: boolean
  model: string
}) {
  const [open, setOpen] = useState(false)
  const analyst = ins.lines.en?.analyst
  const decided = ['aired', 'rejected', 'expired', 'killed', 'switched_off'].includes(ins.status)
  const explained = Boolean(ins.model.analyst && ins.model.analyst !== 'template')
  return (
    <article className={`insight-card status-${ins.status}`}>
      <header>
        <span className="feed-time">{clock(ins.period, ins.t)}</span>
        <span className="type-chip">{ins.type.replace(/_/g, ' ')}</span>
        <span className={`status-chip ${ins.status}`}>{STATUS_LABEL[ins.status] ?? ins.status}</span>
      </header>
      <h4>{analyst?.headline ?? ins.claim}</h4>
      {analyst?.body && <p>{analyst.body}</p>}
      <p className="reasoning">
        <b>Why:</b> {ins.mechanism}
      </p>
      <div className="meta">
        <span className={explained ? 'source model' : 'source'}>analyst: {explained ? ins.model.analyst : 'template'}</span>
        <span className={byModel(analyst?.source) ? 'source model' : 'source'}>lines: {sourceLabel(analyst?.source, model)}</span>
        <span>confidence {Math.round(ins.confidence * 100)}%</span>
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
        {open ? 'Hide details' : 'Reasoning, tools and every language'}
      </button>
      {open && (
        <div className="details">
          <p>
            <b>Claim:</b> {ins.claim}
          </p>
          <p>
            <b>Effect:</b> {ins.consequence}
          </p>
          {ins.tools.length > 0 && (
            <p className="tools">
              <b>Tools called:</b> {ins.tools.join(' · ')}
            </p>
          )}
          {Object.entries(ins.lines).map(([lang, personas]) => (
            <div key={lang} className="lang-block">
              <strong>{lang.toUpperCase()}</strong>
              {Object.entries(personas).map(([persona, line]) => (
                <p key={persona}>
                  <em>{persona.replace('_', ' ')}</em> {line.headline}
                  {line.body ? ` · ${line.body}` : ''} <span className="muted">({sourceLabel(line.source, model)})</span>
                </p>
              ))}
            </div>
          ))}
        </div>
      )}
    </article>
  )
}

function NoteItem({ n }: { n: Note }) {
  const d = n.detail
  if (n.note === 'rejected') {
    const what = d.target === 'explanation' ? 'Explanation rejected' : d.target === 'recap' ? 'Recap line rejected' : 'Line rejected'
    return (
      <li className="rejected">
        <strong>{what}</strong>
        <span>
          {String(d.insight ?? d.body)}
          {d.lang ? ` · ${String(d.lang)} · ${String(d.persona)}` : ''} · attempt {String(d.attempt)}
        </span>
        <span className="muted">{(d.reasons as string[]).join('; ')}</span>
        {d.target !== 'recap' && <q>{String(d.body)}</q>}
      </li>
    )
  }
  if (n.note === 'fallback') {
    return (
      <li className="fallback">
        <strong>Template fallback</strong>
        <span>
          {n.executor.replace('_', ' ')}
          {d.type ? ` · ${String(d.type).replace(/_/g, ' ')}` : ''}
          {d.why ? ` · ${String(d.why)}` : ''}
        </span>
      </li>
    )
  }
  return (
    <li>
      <strong>Dropped repeat</strong>
    </li>
  )
}

interface ProducerProps {
  match: MatchDetail
  room: string
  b: Broadcast
  maps: PitchMaps
  s: Strings
}

export function ProducerDesk({ match, room, b, maps, s }: ProducerProps) {
  const c = useConsole(match, room)
  const all = Object.values(c.insights).sort((x, y) => y.period - x.period || y.t - x.t)
  const waiting = all.filter((i) => i.status === 'awaiting_approval')
  const rundown = all.filter((i) => i.status !== 'awaiting_approval')
  const supervised = c.control.mode === 'supervised'
  const usage = c.crew?.model
  const model = usage?.model ?? 'model'
  const highlight = b.lowerThird?.data.players?.slice(0, 3) ?? []
  const card = (ins: Insight) => (
    <InsightCard
      key={ins.id}
      ins={ins}
      names={maps.names}
      model={model}
      supervised={supervised}
      onApprove={() => c.send({ action: 'approve', insight: ins.id })}
      onReject={() => c.send({ action: 'reject', insight: ins.id })}
    />
  )

  return (
    <div className="producer">
      <section className="monitor">
        <div className="monitor-head">
          <span className="onair">On air</span>
          <a href={`${location.pathname}?match=${match.id}&view=overlay&room=${room}`} target="_blank" rel="noreferrer">
            Clean overlay for OBS or vMix
          </a>
        </div>
        <div className="monitor-screen">
          <Pitch clock={b.clock} {...maps} followed={[]} highlight={highlight} tags={b.tags} trails={[]} />
          <Cards cards={b.cards} />
          <LowerThird packet={b.lowerThird} match={match} />
          {b.recap && <RecapPanel packet={b.recap} onClose={b.dismissRecap} close={s.close} />}
        </div>
      </section>

      <section className="console-controls">
        <div className="tabs">
          <button className={!supervised ? 'on' : ''} onClick={() => c.send({ action: 'mode', value: 'auto' })}>
            Automatic
          </button>
          <button className={supervised ? 'on' : ''} onClick={() => c.send({ action: 'mode', value: 'supervised' })}>
            Approve before air
          </button>
        </div>
        <div className="tabs">
          {usage && (
            <button className={`model ${c.control.model ? 'on' : 'off'}`} onClick={() => c.send({ action: 'model', value: !c.control.model })}>
              {c.control.model ? `Model on: ${model}` : 'Model cut: templates only'}
            </button>
          )}
          <button
            className={`inject ${c.control.unreliable > 0 ? 'on' : ''}`}
            onClick={() => c.send({ action: 'unreliable', value: c.control.unreliable > 0 ? 0 : 0.3 })}
          >
            {c.control.unreliable > 0 ? `Storyteller errors on (${Math.round(c.control.unreliable * 100)}%)` : 'Inject storyteller errors'}
          </button>
          <button className={`kill ${c.control.killed ? 'on' : ''}`} onClick={() => c.send({ action: 'kill', value: !c.control.killed })}>
            {c.control.killed ? 'Graphics off: restore' : 'Kill all graphics'}
          </button>
        </div>
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
        <section className="rundown">
          {supervised && (
            <>
              <h4>Needs approval ({waiting.length})</h4>
              {waiting.length === 0 && <p className="empty">Nothing waiting. New insights stop here until you approve them.</p>}
              {waiting.map(card)}
            </>
          )}
          <h4>Rundown</h4>
          {rundown.length === 0 && <p className="empty">Insights from the crew appear here as the match plays.</p>}
          {rundown.map(card)}
        </section>

        <section className="crew">
          <h4>Insight crew</h4>
          <div className="strip small">
            <div>
              <div className="n">{c.crew?.insights ?? 0}</div>
              <div className="l">insights</div>
            </div>
            <div>
              <div className="n">{c.crew?.rejections ?? 0}</div>
              <div className="l">rejected</div>
            </div>
            <div>
              <div className="n">{c.crew?.fallbacks ?? 0}</div>
              <div className="l">fallbacks</div>
            </div>
            <div>
              <div className="n">${(usage?.cost_usd ?? 0).toFixed(3)}</div>
              <div className="l">credit used</div>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th className="num">Runs</th>
                <th className="num">Time</th>
                <th>Model</th>
              </tr>
            </thead>
            <tbody>
              {AGENTS.map(([key, label, usesModel]) => {
                const u = usage?.agents[key]
                return (
                  <tr key={key}>
                    <td className="name">{label}</td>
                    <td className="num">{c.crew?.executors[key]?.calls ?? 0}</td>
                    <td className="num">{((c.crew?.executors[key]?.ms ?? 0) / 1000).toFixed(1)} s</td>
                    <td>{usesModel ? (u ? `${u.calls} calls, ${u.cached} cached` : '-') : 'rules'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <h4>Crew log</h4>
          {c.notes.length === 0 && <p className="empty">No rejections yet. Inject storyteller errors or cut the model to see recovery.</p>}
          <ul className="notes">
            {c.notes.map((n) => (
              <NoteItem key={n.id} n={n} />
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
