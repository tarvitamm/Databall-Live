import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { MatchClock } from '../clock'
import type { Strings } from '../i18n'
import type { PitchMaps } from '../pitchMaps'
import { download, postToFacebook, postToInstagram, postToX, shareImage, shareLink, shareText } from '../share'
import type { FrameMsg, Lang, MatchDetail, Packet } from '../types'
import { CloseIcon, DownloadIcon, FacebookIcon, InstagramIcon, XIcon } from './Icons'
import { Pitch } from './Pitch'

export function MiniReplay({ match, packet, maps }: { match: MatchDetail; packet: Packet; maps: PitchMaps }) {
  const clock = useMemo(() => new MatchClock(), [])
  const [frames, setFrames] = useState<FrameMsg[]>([])
  const players = useMemo(() => (packet.data.players ?? []).slice(0, 3), [packet])

  useEffect(() => {
    const [start, end] = packet.viz?.window ?? [packet.show_at - 10, packet.show_at]
    let live = true
    api.replay(match.id, packet.period, start - 2, Math.min(end, packet.show_at) + 2).then((r) => live && setFrames(r.frames))
    return () => {
      live = false
    }
  }, [packet, match.id])

  useEffect(() => {
    if (!frames.length) return
    let k = 0
    const timer = setInterval(() => {
      clock.push(frames[k])
      k = (k + 1) % frames.length
    }, 200)
    return () => clearInterval(timer)
  }, [frames, clock])

  const trails = players.map((pid, i) => ({ player: pid, points: frames.map((f) => f.players[pid]).filter(Boolean), tone: i }))
  return (
    <div className="mini-replay">
      <Pitch clock={clock} {...maps} followed={[]} highlight={players} tags={[]} trails={trails} />
      <div className="legend">
        {players.map((pid, i) => (
          <span key={pid}>
            <i className={`tone-${i}`} />
            {maps.names[pid]}
          </span>
        ))}
      </div>
    </div>
  )
}

interface ShareProps {
  packet: Packet
  match: MatchDetail
  maps: PitchMaps
  lang: Lang
  footer: string
  s: Strings
  onClose: () => void
}

export function ShareSheet({ packet, match, maps, lang, footer, s, onClose }: ShareProps) {
  const [blob, setBlob] = useState<Blob | null>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [note, setNote] = useState('')

  useEffect(() => {
    let live = true
    let made: string | null = null
    shareImage(packet, match, maps.teamOf, footer).then((b) => {
      if (!live) return
      made = URL.createObjectURL(b)
      setBlob(b)
      setUrl(made)
    })
    return () => {
      live = false
      if (made) URL.revokeObjectURL(made)
    }
  }, [packet, match, maps.teamOf, footer])

  const text = shareText(packet)
  const link = shareLink(match, lang)
  const instagram = async () => {
    if (!blob) return
    const result = await postToInstagram(blob, text).catch(() => 'saved' as const)
    setNote(result === 'saved' ? s.savedForInstagram : '')
  }

  return (
    <div className="sheet" onClick={onClose}>
      <div className="sheet-card" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-head">
          <b>{s.repost}</b>
          <button className="icon" onClick={onClose} aria-label={s.close}>
            <CloseIcon />
          </button>
        </div>
        <div className="share-preview">{url ? <img src={url} alt={packet.text.headline} /> : <div className="skeleton" />}</div>
        <div className="share-row">
          <button className="social ig" disabled={!blob} onClick={instagram}>
            <InstagramIcon />
            Instagram
          </button>
          <button className="social fb" onClick={() => postToFacebook(link)}>
            <FacebookIcon />
            Facebook
          </button>
          <button className="social x" onClick={() => postToX(text, link)}>
            <XIcon />X
          </button>
          <button className="social" disabled={!blob} onClick={() => blob && download(blob)}>
            <DownloadIcon />
            {s.save}
          </button>
        </div>
        {note && <p className="sheet-note">{note}</p>}
      </div>
    </div>
  )
}
