import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Folder, LibraryResponse, Transcription } from '../../lib/api'
import { LibraryPage } from './LibraryPage'

function transcription(index: number): Transcription {
  return {
    id: `job-${index}`,
    folder_id: null,
    title: `Transcription ${index}`,
    original_filename: `audio-${index}.wav`,
    status: 'completed',
    stage: 'completed',
    progress: 1,
    processed_seconds: null,
    duration_seconds: 60,
    model_name: 'large-v3',
    diarization_mode: 'auto',
    speaker_count: null,
    is_pinned: false,
    position: index,
    viewed_at: null,
    attempt_count: 1,
    error_code: null,
    error_message: null,
    warning_message: null,
    created_at: '2026-07-14T00:00:00Z',
    updated_at: '2026-07-14T00:00:00Z',
  }
}

function folder(index: number): Folder {
  return {
    id: `folder-${index}`,
    parent_id: null,
    name: `Folder ${index}`,
    is_pinned: false,
    position: index,
    created_at: '2026-07-14T00:00:00Z',
    updated_at: '2026-07-14T00:00:00Z',
  }
}

describe('LibraryPage at planned scale', () => {
  afterEach(() => vi.restoreAllMocks())

  it('renders 500 transcriptions and 100 folders without losing the final entries', async () => {
    const folders = Array.from({ length: 100 }, (_, index) => folder(index))
    const payload: LibraryResponse = {
      folder: null,
      breadcrumbs: [],
      folders,
      new_transcriptions: [],
      transcriptions: Array.from({ length: 500 }, (_, index) => transcription(index)),
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.includes('/folders/tree')) return new Response(JSON.stringify(folders.map((item) => ({ ...item, path: item.name }))), { status: 200 })
      if (url.includes('/preferences')) return new Response(JSON.stringify({ default_model: 'large-v3', default_diarization_mode: 'auto', pyannote_configured: false }), { status: 200 })
      return new Response(JSON.stringify(payload), { status: 200 })
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={['/']}><Routes><Route path="/" element={<LibraryPage />} /></Routes></MemoryRouter></QueryClientProvider>)

    expect(await screen.findByText('Transcription 499')).toBeInTheDocument()
    expect(screen.getByText('Folder 99')).toBeInTheDocument()
    expect(screen.getByText('100 pastas · 500 transcrições')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Atualizar' })).not.toBeInTheDocument()
  }, 15_000)
})
