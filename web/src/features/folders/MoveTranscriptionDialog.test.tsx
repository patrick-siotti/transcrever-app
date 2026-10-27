import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { FolderTreeItem, Transcription } from '../../lib/api'
import { MoveTranscriptionDialog } from './MoveTranscriptionDialog'

const item = { id: 'job-1', folder_id: null, title: 'Entrevista' } as Transcription
const folders = [{ id: 'folder-1', path: 'Clientes / Acme', name: 'Acme' }] as FolderTreeItem[]

describe('MoveTranscriptionDialog', () => {
  it('provides root as a keyboard-accessible destination', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<MoveTranscriptionDialog item={item} folders={folders} isSubmitting={false} onClose={vi.fn()} onSubmit={onSubmit} />)

    await user.selectOptions(screen.getByRole('combobox', { name: 'Destino' }), 'folder-1')
    await user.click(screen.getByRole('button', { name: 'Mover' }))

    expect(onSubmit).toHaveBeenCalledWith('folder-1')
    expect(screen.getByRole('option', { name: 'Biblioteca principal' })).toBeInTheDocument()
  })
})
