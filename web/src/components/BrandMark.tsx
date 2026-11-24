import { useId } from 'react'

/** AquaCount mark: a fingerling crossing the counting line. */
export function BrandMark({ className = 'brand-mark', title }: { className?: string; title?: string }) {
  // Unique per instance: a gradient defined inside a hidden copy (e.g. the collapsed sidebar) does not paint.
  const gid = `aq-bg-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  return (
    <svg className={className} viewBox="0 0 64 64" role={title ? 'img' : undefined} aria-hidden={title ? undefined : true} aria-label={title}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1a9cc0" />
          <stop offset="1" stopColor="#0b4f6c" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill={`url(#${gid})`} />
      <path d="M8 38h48" stroke="#e8f8fc" strokeOpacity="0.55" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="2 5" />
      <path d="M17 30c6-9 19-11 27-3l7-6v18l-7-6c-8 8-21 6-27-3z" fill="#f4fbfd" />
      <circle cx="24" cy="28.5" r="2.2" fill="#0b4f6c" />
      <path d="M31 43v8m0 0-3.5-3.5M31 51l3.5-3.5" stroke="#bdf0fb" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  )
}

export function BrandLockup({ sub = true }: { sub?: boolean }) {
  return (
    <>
      <BrandMark />
      <span className="brand-text" style={{ display: 'flex' }}>
        <span className="brand-name">Aqua<em>Count</em></span>
        {sub && <span className="brand-sub">Fingerling intelligence</span>}
      </span>
    </>
  )
}
