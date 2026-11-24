import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { FileCheck2, ScanLine, Users } from 'lucide-react'
import { BrandLockup } from '../../components/BrandMark'
import { DemoBanner } from '../../components/DemoBanner'

/** Decorative: fish passing single-file over the counting line. */
function ChannelArt() {
  return (
    <svg className="channel-art" viewBox="0 0 420 300" aria-hidden>
      <rect x="40" y="20" width="300" height="280" rx="24" fill="#0e2742" stroke="#1e4a72" />
      <path d="M40 160h300" stroke="#4cc6e2" strokeWidth="2" strokeDasharray="6 8" />
      {[[120, 70, '#1baf7a'], [200, 128, '#2a78d6'], [150, 196, '#eb6834'], [240, 250, '#1baf7a']].map(([x, y, c], i) => (
        <g key={i} transform={`translate(${x} ${y}) rotate(90)`}>
          <rect x="-34" y="-20" width="68" height="40" rx="6" fill="none" stroke={c as string} strokeWidth="2" />
          <path d="M-22 0c6-8 18-10 26-3l7-6v18l-7-6c-8 7-20 5-26-3z" fill="#d6eef6" />
        </g>
      ))}
    </svg>
  )
}

export function useCountdown(until: number | null): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!until || until <= Date.now()) return
    const t = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(t)
  }, [until])
  return until ? Math.max(0, Math.ceil((until - now) / 1000)) : 0
}

export function AuthLayout() {
  return (
    <div className="auth">
      <aside className="auth-aside" aria-hidden>
        <div className="auth-logo"><BrandLockup /></div>
        <ChannelArt />
        <div>
          <h2>Every fingerling, counted and on record.</h2>
          <p>Count catfish fingerlings as they pass the camera, grade them by size, and keep a report for every batch you sell.</p>
          <div className="auth-points">
            <div className="auth-point"><ScanLine /><span>Live counting from a fixed channel camera, a phone, or recorded video.</span></div>
            <div className="auth-point"><FileCheck2 /><span>A printable report, a fish-by-fish log and spot-check photos for every run.</span></div>
            <div className="auth-point"><Users /><span>Each operator signs in, so every count shows who ran it.</span></div>
          </div>
        </div>
      </aside>
      <main className="auth-main">
        <div className="auth-demo"><DemoBanner /></div>
        <Outlet />
      </main>
    </div>
  )
}
