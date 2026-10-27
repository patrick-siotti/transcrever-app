import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Check,
  Clock3,
  FileInput,
  FileText,
  FolderOpen,
  LoaderCircle,
  Pin,
  RotateCcw,
  Trash2,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import type { Transcription } from "../../lib/api";
import { formatDate, formatDuration } from "../../lib/format";
import { ElapsedProcessingTime } from "./ElapsedProcessingTime";

interface TranscriptionRowProps {
  item: Transcription;
  pendingAction?: string | undefined;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMove: (item: Transcription, direction: -1 | 1) => void;
  onAction: (
    item: Transcription,
    action: "cancel" | "retry" | "pin" | "open-folder" | "delete" | "move",
  ) => void;
}

const ACTIVE_STATES = new Set([
  "queued",
  "preparing",
  "loading_model",
  "transcribing",
  "diarizing",
  "aligning",
  "exporting",
  "cancel_requested",
]);

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: "Na fila",
    preparing: "Preparando",
    loading_model: "Carregando modelo",
    transcribing: "Transcrevendo",
    diarizing: "Identificando falantes",
    aligning: "Alinhando",
    exporting: "Finalizando",
    completed: "Concluída",
    completed_with_warning: "Concluída com aviso",
    cancel_requested: "Cancelando",
    cancelled: "Cancelada",
    failed: "Falhou",
    interrupted: "Interrompida",
  };
  return labels[status] ?? status;
}

export function TranscriptionRow({
  item,
  pendingAction,
  canMoveUp,
  canMoveDown,
  onMove,
  onAction,
}: TranscriptionRowProps) {
  const active = ACTIVE_STATES.has(item.status);
  const failed = ["failed", "interrupted"].includes(item.status);
  const completed = item.status.startsWith("completed");
  return (
    <article
      className="transcription-row"
      draggable
      onDragStart={(event) => {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("application/x-transcription-id", item.id);
      }}
    >
      <div
        className={`file-token ${failed ? "danger" : completed ? "success" : ""}`}
      >
        {active ? (
          <LoaderCircle className="spin" aria-hidden="true" />
        ) : failed ? (
          <AlertTriangle aria-hidden="true" />
        ) : completed ? (
          <Check aria-hidden="true" />
        ) : (
          <FileText aria-hidden="true" />
        )}
      </div>
      <div className="row-main">
        <div className="row-title-line">
          <Link to={`/transcriptions/${item.id}`}>
            <h3>{item.title}</h3>
          </Link>
          {item.is_pinned && <Pin aria-label="Fixada" />}
          <span className={`status-badge status-${item.status}`}>
            {statusLabel(item.status)}
          </span>
        </div>
        <p>{item.original_filename}</p>
        {active && (
          <div className="progress-line">
            <div
              className="progress-track"
              aria-label={`Progresso: ${Math.round(item.progress * 100)}%`}
            >
              <span style={{ width: `${Math.max(2, item.progress * 100)}%` }} />
            </div>
            <span>{Math.round(item.progress * 100)}%</span>
          </div>
        )}
        {failed && item.error_message && (
          <p className="row-error">{item.error_message}</p>
        )}
      </div>
      <div className="row-meta">
        <span>
          <Clock3 aria-hidden="true" /> {formatDuration(item.duration_seconds)}
        </span>
        {active && item.started_at && (
          <ElapsedProcessingTime startedAt={item.started_at} />
        )}
        <time dateTime={item.updated_at}>{formatDate(item.updated_at)}</time>
      </div>
      <div className="row-actions" aria-label={`Ações de ${item.title}`}>
        {active && (
          <button
            type="button"
            aria-label="Cancelar transcrição"
            title="Cancelar transcrição"
            disabled={Boolean(pendingAction)}
            onClick={() => onAction(item, "cancel")}
          >
            <X aria-hidden="true" />
          </button>
        )}
        {failed && (
          <button
            type="button"
            aria-label="Tentar novamente"
            title="Tentar novamente"
            disabled={Boolean(pendingAction)}
            onClick={() => onAction(item, "retry")}
          >
            <RotateCcw aria-hidden="true" />
          </button>
        )}
        {completed && (
          <button
            type="button"
            aria-label="Abrir pasta"
            title="Abrir pasta"
            disabled={Boolean(pendingAction)}
            onClick={() => onAction(item, "open-folder")}
          >
            <FolderOpen aria-hidden="true" />
          </button>
        )}
        <button
          type="button"
          aria-label={item.is_pinned ? "Desafixar" : "Fixar"}
          title={item.is_pinned ? "Desafixar" : "Fixar"}
          disabled={Boolean(pendingAction)}
          onClick={() => onAction(item, "pin")}
        >
          <Pin aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="Mover para outra pasta"
          title="Mover para outra pasta"
          disabled={Boolean(pendingAction)}
          onClick={() => onAction(item, "move")}
        >
          <FileInput aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="Mover para cima"
          title="Mover para cima"
          disabled={!canMoveUp || Boolean(pendingAction)}
          onClick={() => onMove(item, -1)}
        >
          <ArrowUp aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="Mover para baixo"
          title="Mover para baixo"
          disabled={!canMoveDown || Boolean(pendingAction)}
          onClick={() => onMove(item, 1)}
        >
          <ArrowDown aria-hidden="true" />
        </button>
        <button
          type="button"
          className="danger-action"
          aria-label="Excluir"
          title="Excluir"
          disabled={active || Boolean(pendingAction)}
          onClick={() => onAction(item, "delete")}
        >
          <Trash2 aria-hidden="true" />
        </button>
      </div>
    </article>
  );
}
