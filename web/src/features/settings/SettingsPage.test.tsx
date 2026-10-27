import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import * as api from '../../lib/api'
import { SettingsPage } from './SettingsPage'

vi.mock('../../lib/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../lib/api')>()
  return {
    ...original,
    getPreferences: vi.fn(),
    getDiagnostics: vi.fn(),
    putPreferences: vi.fn(),
  }
})

describe('SettingsPage', () => {
  it('altera e persiste as duas preferências sem perder o evento do select', async () => {
    const user = userEvent.setup()
    vi.mocked(api.getPreferences).mockResolvedValue({ default_model: 'large-v3', default_diarization_mode: 'auto', pyannote_configured: false })
    vi.mocked(api.getDiagnostics).mockResolvedValue({
      version: '0.1.0', database_path: 'db', runs_path: 'runs', trash_path: 'trash', log_path: 'log', worker_enabled: false,
      maintenance: { imported: 0, interrupted: 0, missing_roots: 0, invalid_runs: 0, removed_partials: 0 },
    })
    vi.mocked(api.putPreferences).mockImplementation(async (value) => ({ ...value, pyannote_configured: false }))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(<QueryClientProvider client={queryClient}><MemoryRouter><SettingsPage /></MemoryRouter></QueryClientProvider>)

    await user.selectOptions(await screen.findByRole('combobox', { name: 'Modelo padrão' }), 'medium')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Identificação de falantes' }), 'off')
    await user.click(screen.getByRole('button', { name: 'Salvar preferências' }))

    expect(vi.mocked(api.putPreferences).mock.calls[0]?.[0]).toEqual({ default_model: 'medium', default_diarization_mode: 'off' })
  })
})
