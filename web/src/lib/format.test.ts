import { describe, expect, it } from 'vitest'

import { formatDuration } from './format'

describe('formatDuration', () => {
  it('formats minute and hour durations', () => {
    expect(formatDuration(65)).toBe('1:05')
    expect(formatDuration(3661)).toBe('1:01:01')
  })

  it('handles missing and negative values safely', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(-5)).toBe('0:00')
  })
})
