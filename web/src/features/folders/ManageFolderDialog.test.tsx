import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Folder } from '../../lib/api'
import { ManageFolderDialog } from './ManageFolderDialog'

const folder: Folder = {
  id: 'folder-1',
  parent_id: null,
  name: 'Reuniões',
  is_pinned: false,
  position: 0,
  created_at: '2026-07-14T00:00:00Z',
  updated_at: '2026-07-14T00:00:00Z',
}

describe('ManageFolderDialog', () => {
  it('renames a folder with the trimmed value', async () => {
    const user = userEvent.setup()
    const onRename = vi.fn()
    render(<ManageFolderDialog folder={folder} mode="rename" isSubmitting={false} onClose={vi.fn()} onRename={onRename} onDelete={vi.fn()} />)

    await user.clear(screen.getByRole('textbox', { name: 'Novo nome' }))
    await user.type(screen.getByRole('textbox', { name: 'Novo nome' }), '  Clientes  ')
    await user.click(screen.getByRole('button', { name: 'Salvar nome' }))

    expect(onRename).toHaveBeenCalledWith('Clientes')
  })

  it('closes on Escape and exposes destructive copy before deletion', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const onDelete = vi.fn()
    render(<ManageFolderDialog folder={folder} mode="delete" isSubmitting={false} onClose={onClose} onRename={vi.fn()} onDelete={onDelete} />)

    expect(screen.getByRole('alertdialog')).toHaveTextContent('também serão movidas para a lixeira')
    await user.keyboard('{Escape}')

    expect(onClose).toHaveBeenCalledOnce()
    expect(onDelete).not.toHaveBeenCalled()
  })
})
