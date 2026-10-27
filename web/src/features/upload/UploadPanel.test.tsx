import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { UploadPanel } from './UploadPanel'

describe('UploadPanel', () => {
  it('shows a specific recovery message when submitted without a file', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<UploadPanel isSubmitting={false} onSubmit={onSubmit} />)

    await user.click(screen.getByRole('button', { name: 'Enviar para transcrição' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Selecione um arquivo de áudio ou vídeo.')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits a selected file with the derived title', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<UploadPanel isSubmitting={false} onSubmit={onSubmit} />)
    const file = new File(['media'], 'reuniao.mkv', { type: 'video/x-matroska' })

    await user.upload(screen.getByLabelText(/Escolha um áudio ou vídeo/), file)
    await user.click(screen.getByRole('button', { name: 'Enviar para transcrição' }))

    expect(onSubmit).toHaveBeenCalledWith({
      file,
      title: 'reuniao',
      modelName: 'large-v3',
      diarizationMode: 'pyannote',
    })
  })

  it('accepts a video dropped into the upload area', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<UploadPanel isSubmitting={false} onSubmit={onSubmit} />)
    const file = new File(['video'], 'entrevista.mp4', { type: 'video/mp4' })

    fireEvent.drop(screen.getByText('Escolha um áudio ou vídeo').closest('label')!, {
      dataTransfer: { files: [file] },
    })
    await user.click(screen.getByRole('button', { name: 'Enviar para transcrição' }))

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ file, title: 'entrevista' }))
  })

  it('keeps model and diarization in settings instead of exposing advanced controls', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(
      <UploadPanel
        isSubmitting={false}
        defaultModel="medium"
        defaultDiarizationMode="clustering"
        onSubmit={onSubmit}
      />,
    )
    const file = new File(['media'], 'reuniao.mkv', { type: 'video/x-matroska' })

    expect(screen.queryByRole('combobox', { name: 'Identificação de falantes' })).not.toBeInTheDocument()
    expect(screen.queryByText('Modelo')).not.toBeInTheDocument()

    await user.upload(screen.getByLabelText(/Escolha um áudio ou vídeo/), file)
    await user.click(screen.getByRole('button', { name: 'Enviar para transcrição' }))

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      modelName: 'medium',
      diarizationMode: 'clustering',
    }))
  })
})
