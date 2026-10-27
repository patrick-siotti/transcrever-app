import { useEffect, useRef, type FormEvent } from "react";
import { FolderInput, X } from "lucide-react";

import type { FolderTreeItem, Transcription } from "../../lib/api";
import { useModalKeyboard } from "../../lib/useModalKeyboard";

interface MoveTranscriptionDialogProps {
  item: Transcription | undefined;
  folders: FolderTreeItem[];
  isSubmitting: boolean;
  onClose: () => void;
  onSubmit: (folderId: string | null) => void;
}

export function MoveTranscriptionDialog({
  item,
  folders,
  isSubmitting,
  onClose,
  onSubmit,
}: MoveTranscriptionDialogProps) {
  const selectRef = useRef<HTMLSelectElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  useModalKeyboard(Boolean(item), dialogRef, onClose);
  useEffect(() => {
    if (item) selectRef.current?.focus();
  }, [item]);
  if (!item) return null;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const target = String(data.get("folder_id") ?? "");
    onSubmit(target || null);
  }

  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="move-dialog-title"
      >
        <div className="dialog-heading">
          <span>
            <FolderInput aria-hidden="true" />
          </span>
          <div>
            <h2 id="move-dialog-title">Mover transcrição</h2>
            <p>Escolha onde organizar “{item.title}”.</p>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="Fechar"
            title="Fechar"
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </button>
        </div>
        <form onSubmit={submit}>
          <label>
            <span>Destino</span>
            <select
              ref={selectRef}
              name="folder_id"
              defaultValue={item.folder_id ?? ""}
            >
              <option value="">Biblioteca principal</option>
              {folders.map((folder) => (
                <option
                  key={folder.id}
                  value={folder.id}
                  disabled={folder.id === item.folder_id}
                >
                  {folder.path}
                </option>
              ))}
            </select>
          </label>
          <div className="dialog-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={onClose}
            >
              Cancelar
            </button>
            <button
              className="primary-button"
              type="submit"
              disabled={isSubmitting}
            >
              Mover
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
