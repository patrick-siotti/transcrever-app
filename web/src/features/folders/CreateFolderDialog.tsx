import { useEffect, useRef, useState, type FormEvent } from 'react'
import { FolderPlus, X } from 'lucide-react'

import { useModalKeyboard } from '../../lib/useModalKeyboard'

interface CreateFolderDialogProps {
  open: boolean
  isSubmitting: boolean
  onClose: () => void
  onSubmit: (name: string) => void
}

export function CreateFolderDialog({ open, isSubmitting, onClose, onSubmit }: CreateFolderDialogProps) {
  const [name, setName] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLElement>(null)
  useModalKeyboard(open, dialogRef, onClose)

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  if (!open) return null

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (name.trim()) onSubmit(name.trim())
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <section ref={dialogRef} className="dialog" role="dialog" aria-modal="true" aria-labelledby="folder-dialog-title">
        <div className="dialog-heading">
          <span><FolderPlus aria-hidden="true" /></span>
          <div><h2 id="folder-dialog-title">Nova pasta</h2></div>
          <button className="icon-button" type="button" aria-label="Fechar" title="Fechar" onClick={onClose}><X aria-hidden="true" /></button>
        </div>
        <form onSubmit={submit}>
          <label><span>Nome da pasta</span><input ref={inputRef} value={name} maxLength={160} onChange={(event) => setName(event.currentTarget.value)} /></label>
          <div className="dialog-actions"><button className="secondary-button" type="button" onClick={onClose}>Cancelar</button><button className="primary-button" type="submit" disabled={!name.trim() || isSubmitting}>{isSubmitting ? 'Criando…' : 'Criar pasta'}</button></div>
        </form>
      </section>
    </div>
  )
}
