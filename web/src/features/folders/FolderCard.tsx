import { ArrowDown, ArrowUp, Folder as FolderIcon, Pin } from "lucide-react";
import { Link } from "react-router-dom";

import type { Folder } from "../../lib/api";

interface FolderCardProps {
  folder: Folder;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onDropTranscription?: (transcriptionId: string, folderId: string) => void;
  onMove: (folder: Folder, direction: -1 | 1) => void;
  onTogglePin: (folder: Folder) => void;
}

export function FolderCard({
  folder,
  canMoveUp,
  canMoveDown,
  onDropTranscription,
  onMove,
  onTogglePin,
}: FolderCardProps) {
  return (
    <article
      className="folder-card"
      onDragOver={(event) => {
        if (
          event.dataTransfer.types.includes("application/x-transcription-id")
        ) {
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
        }
      }}
      onDrop={(event) => {
        const transcriptionId = event.dataTransfer.getData(
          "application/x-transcription-id",
        );
        if (transcriptionId) {
          event.preventDefault();
          onDropTranscription?.(transcriptionId, folder.id);
        }
      }}
    >
      <Link className="folder-card-link" to={`/folders/${folder.id}`}>
        <span className="folder-icon">
          <FolderIcon aria-hidden="true" />
        </span>
        <span>
          <strong>{folder.name}</strong>
          <small>Pasta</small>
        </span>
      </Link>
      <div className="folder-actions">
        <button
          type="button"
          aria-label={
            folder.is_pinned
              ? `Desafixar ${folder.name}`
              : `Fixar ${folder.name}`
          }
          title={
            folder.is_pinned
              ? `Desafixar ${folder.name}`
              : `Fixar ${folder.name}`
          }
          onClick={() => onTogglePin(folder)}
        >
          <Pin aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label={`Mover ${folder.name} para cima`}
          title={`Mover ${folder.name} para cima`}
          disabled={!canMoveUp}
          onClick={() => onMove(folder, -1)}
        >
          <ArrowUp aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label={`Mover ${folder.name} para baixo`}
          title={`Mover ${folder.name} para baixo`}
          disabled={!canMoveDown}
          onClick={() => onMove(folder, 1)}
        >
          <ArrowDown aria-hidden="true" />
        </button>
      </div>
    </article>
  );
}
