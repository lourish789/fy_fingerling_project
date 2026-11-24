import { describe, expect, it } from 'vitest'
import { classShares, dayGroup, describeDevice, formatDuration, formatNumber, normaliseCounts, passwordStrength } from './format'
import { niceScale } from '../components/DailyChart'

describe('formatting', () => {
  it('compacts only large numbers', () => {
    expect(formatNumber(9999, true)).toBe(new Intl.NumberFormat().format(9999))
    expect(formatNumber(12_900, true)).toMatch(/12\.9\s?K/i)
    expect(formatNumber(null)).toBe('—')
  })

  it('formats durations', () => {
    expect(formatDuration(42)).toBe('42 s')
    expect(formatDuration(120)).toBe('2 min')
    expect(formatDuration(3700)).toBe('1 h 1 min')
  })

  it('fills missing class keys with zero', () => {
    expect(normaliseCounts({ total: 3, fingerling: 3 })).toEqual({ total: 3, fingerling: 3, post_fingerling: 0, juvenile: 0, unknown: 0 })
    expect(classShares(normaliseCounts({ fingerling: 3, juvenile: 1 })).fingerling).toBeCloseTo(0.75)
  })

  it('groups by local day', () => {
    const now = new Date(2026, 10, 24, 15, 0)
    expect(dayGroup(new Date(2026, 10, 24, 8, 0).toISOString(), now)).toBe('Today')
    expect(dayGroup(new Date(2026, 10, 23, 23, 0).toISOString(), now)).toBe('Yesterday')
  })

  it('names devices in the sessions list', () => {
    expect(describeDevice('Mozilla/5.0 (Linux; Android 14) AppleWebKit Chrome/130 Mobile Safari/537.36')).toEqual({ label: 'Chrome on Android', kind: 'phone' })
    expect(describeDevice('Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/130 Safari/537.36 Edg/130').label).toBe('Edge on Windows')
  })

  it('rates passwords by length first, like the server', () => {
    expect(passwordStrength('short')).toBe(1)
    expect(passwordStrength('aaaaaaaaaaaa')).toBe(1) // too few distinct characters
    expect(passwordStrength('fingerlings')).toBe(2)
    expect(passwordStrength('catfish in the channel')).toBe(4)
  })
})

describe('chart axis', () => {
  it('rounds the top to clean ticks', () => {
    expect(niceScale(11)).toEqual({ top: 15, step: 5 })
    expect(niceScale(4300)).toEqual({ top: 6000, step: 2000 }) // 0 / 2,000 / 4,000 / 6,000
    expect(niceScale(0)).toEqual({ top: 4, step: 1 })
  })
})
