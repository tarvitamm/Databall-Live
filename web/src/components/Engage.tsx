import { badgeFor } from '../badges'
import type { Strings } from '../i18n'
import { clock } from '../i18n'
import type { Lang, Packet } from '../types'
import type { Broadcast, Call } from '../useBroadcast'
import { CheckIcon, CloseIcon, FlameIcon } from './Icons'

export function Badge({ p, s }: { p: Packet; s: Strings }) {
  const badge = badgeFor(p, s)
  return badge ? <span className={`badge ${badge.tone}`}>{badge.label}</span> : null
}

export function ScoreChip({ b, s }: { b: Broadcast; s: Strings }) {
  return (
    <span className={`score-chip ${b.score.streak >= 2 ? 'hot' : ''}`}>
      <FlameIcon />
      {b.score.streak}
      <i />
      {b.score.points} {s.pts}
    </span>
  )
}

function left(call: Call, now: { period: number; t: number }): number {
  const { opens, closes, period } = call.prompt
  if (period !== now.period) return 0
  return Math.max(0, Math.min(1, (closes - now.t) / Math.max(closes - opens, 1)))
}

function Options({ call, b, lang }: { call: Call; b: Broadcast; lang: Lang }) {
  const picked = b.picks[call.prompt.id]
  return (
    <div className="call-options">
      {call.prompt.options.map((o) => {
        const state = call.result ? (o.id === call.result.answer ? 'right' : picked === o.id ? 'wrong' : '') : picked === o.id ? 'picked' : ''
        return (
          <button key={o.id} className={state} disabled={Boolean(picked) || Boolean(call.result)} onClick={() => b.pick(call.prompt.id, o.id)}>
            {o.label[lang] ?? o.label.en}
            {state === 'right' && <CheckIcon />}
          </button>
        )
      })}
    </div>
  )
}

export function PredictionPopup({ call, b, s, lang, onClose }: { call: Call; b: Broadcast; s: Strings; lang: Lang; onClose: () => void }) {
  const picked = b.picks[call.prompt.id]
  return (
    <div className="popup call" role="status">
      <div className="popup-head">
        <span className="dot" />
        {s.liveCall} · {clock(call.prompt.period, call.prompt.opens)}
        <button className="icon" onClick={onClose} aria-label={s.close}>
          <CloseIcon />
        </button>
      </div>
      <b>{call.prompt.question[lang] ?? call.prompt.question.en}</b>
      <Options call={call} b={b} lang={lang} />
      {picked ? (
        <p className="call-note">
          {s.lockedIn}. {s.waitingResult}.
        </p>
      ) : (
        <div className="countdown">
          <i style={{ width: `${left(call, b.now) * 100}%` }} />
        </div>
      )}
    </div>
  )
}

export function ResultPopup({ call, b, s, lang, onClose }: { call: Call; b: Broadcast; s: Strings; lang: Lang; onClose: () => void }) {
  const won = b.picks[call.prompt.id] === call.result?.answer
  const gained = b.score.last?.id === call.prompt.id ? b.score.last.gained : 0
  return (
    <div className={`popup result ${won ? 'won' : 'lost'}`} role="status">
      <div className="popup-head">
        {s.liveCall}
        <button className="icon" onClick={onClose} aria-label={s.close}>
          <CloseIcon />
        </button>
      </div>
      <div className="result-row">
        <b>{won ? s.calledIt : s.notThisTime}</b>
        {won && <span className="gain">+{gained}</span>}
      </div>
      <p>{call.result?.detail[lang] ?? call.result?.detail.en}</p>
      {won && b.score.streak >= 2 && (
        <p className="streak-line">
          <FlameIcon />
          {b.score.streak} {s.streak}
        </p>
      )}
    </div>
  )
}

export function CallsList({ b, s, lang }: { b: Broadcast; s: Strings; lang: Lang }) {
  const calls = b.calls.slice(0, 3)
  if (!calls.length) return null
  return (
    <>
      <h5 className="app-section">{s.yourCalls}</h5>
      {calls.map((call) => {
        const picked = b.picks[call.prompt.id]
        const status = call.result
          ? picked
            ? picked === call.result.answer
              ? s.calledIt
              : s.notThisTime
            : s.missed
          : picked
            ? s.waitingResult
            : ''
        return (
          <article key={call.prompt.id} className={`call-card ${call.result && picked === call.result.answer ? 'won' : ''}`}>
            <span className="time">{clock(call.prompt.period, call.prompt.opens)}</span>
            <b>{call.prompt.question[lang] ?? call.prompt.question.en}</b>
            <Options call={call} b={b} lang={lang} />
            {status && <p className="call-note">{status}{call.result ? ` · ${call.result.detail[lang] ?? call.result.detail.en}` : ''}</p>}
          </article>
        )
      })}
    </>
  )
}
