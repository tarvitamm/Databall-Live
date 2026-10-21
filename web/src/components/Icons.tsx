const base = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true }

export function PlayIcon() {
  return (
    <svg {...base}>
      <path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function PauseIcon() {
  return (
    <svg {...base}>
      <path d="M8 5v14M16 5v14" strokeWidth={2.6} />
    </svg>
  )
}

export function ReplayIcon() {
  return (
    <svg {...base}>
      <path d="M4 12a8 8 0 1 0 2.4-5.7" />
      <path d="M4 4.5v4.2h4.2" />
      <path d="M10.5 9.5v5l4-2.5z" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function ShareIcon() {
  return (
    <svg {...base}>
      <path d="M12 15V4M8 8l4-4 4 4" />
      <path d="M5 12v6.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V12" />
    </svg>
  )
}

export function InstagramIcon() {
  return (
    <svg {...base}>
      <rect x="3.5" y="3.5" width="17" height="17" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.3" cy="6.7" r="0.9" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function FacebookIcon() {
  return (
    <svg {...base}>
      <path d="M14.5 8.5H17V5h-2.5C12 5 10.5 6.6 10.5 9v2H8v3.5h2.5V21H14v-6.5h2.6l.6-3.5H14V9.2c0-.4.2-.7.5-.7z" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function XIcon() {
  return (
    <svg {...base}>
      <path d="M4.5 4.5l15 15M19.5 4.5l-15 15" strokeWidth={2.2} />
    </svg>
  )
}

export function DownloadIcon() {
  return (
    <svg {...base}>
      <path d="M12 4v11M8 11l4 4 4-4" />
      <path d="M5 19.5h14" />
    </svg>
  )
}

export function CloseIcon() {
  return (
    <svg {...base}>
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  )
}

export function Mark() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 2a10 10 0 0 1 0 20z" fill="currentColor" />
      <circle cx="12" cy="12" r="3" fill="var(--paper)" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  )
}

export function FlameIcon() {
  return (
    <svg {...base} width={14} height={14}>
      <path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.2 1.2-3.6 2.3-4.6.2 1.6 1 2.6 2.2 3.1-.4-3 .1-5.6.5-8.5z" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function CheckIcon() {
  return (
    <svg {...base}>
      <path d="M5 12.5l4.5 4.5L19 7.5" strokeWidth={2.4} />
    </svg>
  )
}
