import { useEffect, useRef, useState, type FormEvent } from "react";
import { Pencil, Trash2, X } from "lucide-react";

import type { Folder } from "../../lib/api";
import { useModalKeyboard } from "../../lib/useModalKeyboard";

interface ManageFolderDialogProps {
  folder: Folder | undefined;
  mode: "rename" | "delete" | undefined;
  isSubmitting: boolean;
  onClose: () => void;
  onRename: (name: string) => void;
  onDelete: () => void;
}

export function ManageFolderDialog({
  folder,
  mode,
  isSubmitting,
  onClose,
  onRename,
  onDelete,
}: ManageFolderDialogProps) {
  const [name, setName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  useModalKeyboard(Boolean(folder && mode), dialogRef, onClose);
  useEffect(() => {
    setName(folder?.name ?? "");
    if (folder && mode === "rename") inputRef.current?.focus();
  }, [folder, mode]);
  if (!folder || !mode) return null;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mode === "rename" && name.trim()) onRename(name.trim());
    if (mode === "delete") onDelete();
  }

  const deleting = mode === "delete";
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
        role={deleting ? "alertdialog" : "dialog"}
        aria-modal="true"
        aria-labelledby="manage-folder-title"
      >
        <div className="dialog-heading">
          <span>
            {deleting ? (
              <Trash2 aria-hidden="true" />
            ) : (
              <Pencil aria-hidden="true" />
            )}
          </span>
          <div>
            <h2 id="manage-folder-title">
              {deleting ? "Excluir pasta?" : "Renomear pasta"}
            </h2>
            {deleting && (
              <p>
                As transcrições dentro dela também serão movidas para a lixeira.
              </p>
            )}
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
          {deleting ? (
            <p>
              Confirme a exclusão de <strong>{folder.name}</strong>. Você poderá
              restaurar as transcrições individualmente pela lixeira.
            </p>
          ) : (
            <label>
              <span>Novo nome</span>
              <input
                ref={inputRef}
                value={name}
                maxLength={160}
                onChange={(event) => setName(event.currentTarget.value)}
              />
            </label>
          )}
          <div className="dialog-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={onClose}
            >
              Cancelar
            </button>
            <button
              className={deleting ? "danger-button" : "primary-button"}
              type="submit"
              disabled={isSubmitting || (!deleting && !name.trim())}
            >
              {deleting ? "Excluir pasta" : "Salvar nome"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
