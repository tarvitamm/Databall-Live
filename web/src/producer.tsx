import { useEffect, useRef, useState } from 'react'
import { api, openSocket, type Stream } from './api'
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
  why?: Record<string, { claim: string; mechanism: string; consequence: string; lang: string }>
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

const TYPES = ['chain', 'decoy_run', 'pressure_shift', 'momentum_swing', 'counter_press', 'between_lines_gap', 'overload', 'fatigue', 'match_state', 'speed_tag']
const AGENTS: [string, boolean][] = [
  ['moment_router', false],
  ['tactical_analyst', true],
  ['player_lens', true],
  ['editor', false],
  ['storyteller', true],
  ['verifier', false],
  ['recapper', true],
  ['producer', false],
]

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

type P = Strings['prod']

function sourceLabel(source: string | undefined, model: string, t: P): string {
  if (source === 'model') return model
  if (source === 'cached') return `${model}, ${t.cachedBy}`
  if (source === 'fallback') return t.fallback
  return t.template
}

function byModel(source: string | undefined): boolean {
  return source === 'model' || source === 'cached'
}

interface CardProps {
  ins: Insight
  names: Record<string, string>
  onApprove: () => void
  onReject: () => void
  supervised: boolean
  model: string
  s: Strings
  lang: string
}

function InsightCard({ ins, names, onApprove, onReject, supervised, model, s, lang }: CardProps) {
  const [open, setOpen] = useState(false)
  const t = s.prod
  const line = ins.lines[lang]?.analyst ?? ins.lines.en?.analyst
  const why = ins.why?.[lang] ?? { claim: ins.claim, mechanism: ins.mechanism, consequence: ins.consequence, lang: 'en' }
  const decided = ['aired', 'rejected', 'expired', 'killed', 'switched_off'].includes(ins.status)
  const explained = Boolean(ins.model.analyst && ins.model.analyst !== 'template')
  return (
    <article className={`insight-card status-${ins.status}`}>
      <header>
        <span className="feed-time">{clock(ins.period, ins.t)}</span>
        <span className="type-chip">{s.kind[ins.type] ?? ins.type.replace(/_/g, ' ')}</span>
        <span className={`status-chip ${ins.status}`}>{s.status[ins.status] ?? ins.status}</span>
      </header>
      <h4>{line?.headline ?? why.claim}</h4>
      {line?.body && <p>{line.body}</p>}
      <p className="reasoning">
        <b>{t.why}:</b> {why.mechanism}
      </p>
      <div className="meta">
        <span className={explained ? 'source model' : 'source'}>
          {t.analyst}: {explained ? ins.model.analyst : t.template}
        </span>
        <span className={byModel(line?.source) ? 'source model' : 'source'}>
          {t.lines}: {sourceLabel(line?.source, model, t)}
        </span>
        <span>
          {t.confidence} {Math.round(ins.confidence * 100)}%
        </span>
        {ins.entities.players?.length ? <span>{ins.entities.players.map((p) => names[p] ?? p).join(', ')}</span> : null}
      </div>
      {supervised && !decided && (
        <div className="actions">
          <button className="approve" onClick={onApprove}>
            {t.approve}
          </button>
          <button className="reject" onClick={onReject}>
            {t.reject}
          </button>
        </div>
      )}
      <button className="link" onClick={() => setOpen(!open)}>
        {open ? t.hide : t.details}
      </button>
      {open && (
        <div className="details">
          <p>
            <b>{t.claim}:</b> {why.claim}
          </p>
          <p>
            <b>{t.effect}:</b> {why.consequence}
          </p>
          {ins.tools.length > 0 && (
            <p className="tools">
              <b>{t.tools}:</b> {ins.tools.join(' · ')}
            </p>
          )}
          {Object.entries(ins.lines).map(([code, personas]) => (
            <div key={code} className="lang-block">
              <strong>{code.toUpperCase()}</strong>
              {Object.entries(personas).map(([persona, l]) => (
                <p key={persona}>
                  <em>{persona.replace('_', ' ')}</em> {l.headline}
                  {l.body ? ` · ${l.body}` : ''} <span className="muted">({sourceLabel(l.source, model, t)})</span>
                </p>
              ))}
            </div>
          ))}
        </div>
      )}
    </article>
  )
}

function NoteItem({ n, s }: { n: Note; s: Strings }) {
  const d = n.detail
  const t = s.prod
  if (n.note === 'rejected') {
    const what = d.target === 'explanation' ? t.explanationRejected : d.target === 'recap' ? t.recapRejected : t.lineRejected
    return (
      <li className="rejected">
        <strong>{what}</strong>
        <span>
          {String(d.insight ?? d.body)}
          {d.lang ? ` · ${String(d.lang)}` : ''}
          {d.persona ? ` · ${String(d.persona)}` : ''} · {t.attempt} {String(d.attempt)}
        </span>
        <span className="muted">{(d.reasons as string[]).join('; ')}</span>
        {d.target !== 'recap' && <q>{String(d.body)}</q>}
      </li>
    )
  }
  if (n.note === 'fallback') {
    return (
      <li className="fallback">
        <strong>{t.templateFallback}</strong>
        <span>
          {s.agents[n.executor] ?? n.executor}
          {d.type ? ` · ${s.kind[String(d.type)] ?? String(d.type).replace(/_/g, ' ')}` : ''}
          {d.why ? ` · ${String(d.why)}` : ''}
        </span>
      </li>
    )
  }
  return (
    <li>
      <strong>{t.dropped}</strong>
    </li>
  )
}

function TalkingPoints({ match, lang, title }: { match: MatchDetail; lang: string; title: string }) {
  const [points, setPoints] = useState<{ lang: string; items: string[] }>({ lang: '', items: [] })
  useEffect(() => {
    let live = true
    api.talkingPoints(match.id, lang).then((items) => live && setPoints({ lang, items })).catch(() => {})
    return () => {
      live = false
    }
  }, [match.id, lang])
  if (!points.items.length) return null
  return (
    <section className="talking">
      <h4>{title}</h4>
      <ul>
        {points.items.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
    </section>
  )
}

interface ProducerProps {
  match: MatchDetail
  room: string
  b: Broadcast
  maps: PitchMaps
  s: Strings
  lang: string
}

export function ProducerDesk({ match, room, b, maps, s, lang }: ProducerProps) {
  const c = useConsole(match, room)
  const t = s.prod
  const all = Object.values(c.insights).sort((x, y) => y.period - x.period || y.t - x.t)
  const waiting = all.filter((i) => i.status === 'awaiting_approval')
  const rundown = all.filter((i) => i.status !== 'awaiting_approval')
  const supervised = c.control.mode === 'supervised'
  const usage = c.crew?.model
  const model = usage?.model ?? 'model'
  const highlight = b.lowerThird?.data.players?.slice(0, 3) ?? []
  const shown = b.lowerThird ?? b.feed[0]
  const onAir = shown ? (({ received: _received, ...rest }) => rest)(shown) : null
  const card = (ins: Insight) => (
    <InsightCard
      key={ins.id}
      ins={ins}
      names={maps.names}
      model={model}
      supervised={supervised}
      s={s}
      lang={lang}
      onApprove={() => c.send({ action: 'approve', insight: ins.id })}
      onReject={() => c.send({ action: 'reject', insight: ins.id })}
    />
  )

  return (
    <div className="producer">
      <section className="monitor">
        <div className="monitor-head">
          <span className="onair">{t.onAir}</span>
          <a href={`${location.pathname}?match=${match.id}&view=overlay&room=${room}`} target="_blank" rel="noreferrer">
            {t.overlay}
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
            {t.auto}
          </button>
          <button className={supervised ? 'on' : ''} onClick={() => c.send({ action: 'mode', value: 'supervised' })}>
            {t.supervised}
          </button>
        </div>
        <div className="tabs">
          {usage && (
            <button className={`model ${c.control.model ? 'on' : 'off'}`} onClick={() => c.send({ action: 'model', value: !c.control.model })}>
              {c.control.model ? `${t.modelOn}: ${model}` : t.modelCut}
            </button>
          )}
          <button
            className={`inject ${c.control.unreliable > 0 ? 'on' : ''}`}
            onClick={() => c.send({ action: 'unreliable', value: c.control.unreliable > 0 ? 0 : 0.3 })}
          >
            {c.control.unreliable > 0 ? `${t.injectOn} (${Math.round(c.control.unreliable * 100)}%)` : t.inject}
          </button>
          <button className={`kill ${c.control.killed ? 'on' : ''}`} onClick={() => c.send({ action: 'kill', value: !c.control.killed })}>
            {c.control.killed ? t.restore : t.kill}
          </button>
        </div>
        <div className="type-toggles">
          {TYPES.map((type) => {
            const off = c.control.disabled.includes(type)
            return (
              <button key={type} className={off ? 'off' : 'on'} onClick={() => c.send({ action: 'type', value: type, on: off })}>
                {s.types[type] ?? type}
              </button>
            )
          })}
        </div>
      </section>

      <details className="packet-view">
        <summary>
          {t.packet}
          <span>{t.packetNote}</span>
        </summary>
        {onAir ? <pre>{JSON.stringify(onAir, null, 2)}</pre> : <p className="empty">{t.packetEmpty}</p>}
      </details>

      <TalkingPoints match={match} lang={lang} title={t.talking} />

      <div className="console-grid">
        <section className="rundown">
          {supervised && (
            <>
              <h4>
                {t.needsApproval} ({waiting.length})
              </h4>
              {waiting.length === 0 && <p className="empty">{t.nothingWaiting}</p>}
              {waiting.map(card)}
            </>
          )}
          <h4>{t.rundown}</h4>
          {rundown.length === 0 && <p className="empty">{t.rundownEmpty}</p>}
          {rundown.map(card)}
        </section>

        <section className="crew">
          <h4>{t.crew}</h4>
          <div className="strip small">
            <div>
              <div className="n">{c.crew?.insights ?? 0}</div>
              <div className="l">{t.insights}</div>
            </div>
            <div>
              <div className="n">{c.crew?.rejections ?? 0}</div>
              <div className="l">{t.rejected}</div>
            </div>
            <div>
              <div className="n">{c.crew?.fallbacks ?? 0}</div>
              <div className="l">{t.fallbacks}</div>
            </div>
            <div>
              <div className="n">${(usage?.cost_usd ?? 0).toFixed(3)}</div>
              <div className="l">{t.credit}</div>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t.agent}</th>
                <th className="num">{t.runs}</th>
                <th className="num">{t.time}</th>
                <th>{t.model}</th>
              </tr>
            </thead>
            <tbody>
              {AGENTS.map(([key, usesModel]) => {
                const u = usage?.agents[key]
                return (
                  <tr key={key}>
                    <td className="name">{s.agents[key]}</td>
                    <td className="num">{c.crew?.executors[key]?.calls ?? 0}</td>
                    <td className="num">{((c.crew?.executors[key]?.ms ?? 0) / 1000).toFixed(1)} s</td>
                    <td>{usesModel ? (u ? `${u.calls} ${t.calls}, ${u.cached} ${t.cached}` : '-') : t.rules}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <h4>{t.log}</h4>
          {c.notes.length === 0 && <p className="empty">{t.logEmpty}</p>}
          <ul className="notes">
            {c.notes.map((n) => (
              <NoteItem key={n.id} n={n} s={s} />
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
