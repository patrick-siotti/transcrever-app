import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ElapsedProcessingTime } from './ElapsedProcessingTime'

describe('ElapsedProcessingTime', () => {
  afterEach(() => vi.useRealTimers())

  it('updates the visible processing time every second', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-14T18:00:00Z'))
    render(<ElapsedProcessingTime startedAt="2026-07-14T17:58:50Z" />)

    expect(screen.getByText('Em processamento há 1 min 10 s')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1000))
    expect(screen.getByText('Em processamento há 1 min 11 s')).toBeInTheDocument()
  })
})
