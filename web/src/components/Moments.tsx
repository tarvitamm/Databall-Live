import { useEffect, useState } from 'react'
import type { Strings } from '../i18n'
import type { PitchMaps } from '../pitchMaps'
import { download, postToFacebook, postToInstagram, postToX, shareImage, shareLink, shareText } from '../share'
import type { Lang, MatchDetail, Packet } from '../types'
import { CloseIcon, DownloadIcon, FacebookIcon, InstagramIcon, XIcon } from './Icons'

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
