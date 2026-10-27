import { useId, useRef, useState, type DragEvent, type FormEvent } from "react";
import { FileAudio, Upload, Users, X } from "lucide-react";

import type { UploadInput } from "../../lib/api";

interface UploadPanelProps {
  isSubmitting: boolean;
  defaultModel?: string | undefined;
  defaultDiarizationMode?: UploadInput["diarizationMode"] | undefined;
  uploadProgress?: number | undefined;
  onCancel?: (() => void) | undefined;
  onSubmit: (input: UploadInput) => void;
}

export function UploadPanel({
  isSubmitting,
  defaultModel = "large-v3",
  defaultDiarizationMode = "pyannote",
  uploadProgress = 0,
  onCancel,
  onSubmit,
}: UploadPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [speakerCount, setSpeakerCount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();

  function selectFile(selected: File | null) {
    setFile(selected);
    setError(null);
    if (selected && !title) setTitle(selected.name.replace(/\.[^.]+$/, ""));
  }

  function dropFile(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(false);
    selectFile(event.dataTransfer.files[0] ?? null);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Selecione um arquivo de áudio ou vídeo.");
      return;
    }
    if (!title.trim()) {
      setError("Informe um título para encontrar esta transcrição depois.");
      return;
    }
    setError(null);
    onSubmit({
      file,
      title: title.trim(),
      modelName: defaultModel,
      diarizationMode: defaultDiarizationMode,
      ...(speakerCount ? { speakerCount: Number(speakerCount) } : {}),
    });
  }

  return (
    <section className="upload-panel" aria-labelledby="upload-title">
      <div className="upload-heading">
        <h2 id="upload-title">Nova transcrição</h2>
      </div>

      <form onSubmit={submit} noValidate>
        <label
          className={`drop-zone ${file ? "has-file" : ""} ${isDragging ? "is-dragging" : ""}`}
          htmlFor={inputId}
          onDragEnter={(event) => {
            event.preventDefault();
            setIsDragging(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
          }}
          onDragLeave={(event) => {
            if (
              !event.currentTarget.contains(event.relatedTarget as Node | null)
            )
              setIsDragging(false);
          }}
          onDrop={dropFile}
        >
          <input
            ref={fileInputRef}
            id={inputId}
            type="file"
            accept="audio/*,video/*,.mkv"
            onChange={(event) => {
              selectFile(event.currentTarget.files?.[0] ?? null);
            }}
          />
          {file ? (
            <FileAudio aria-hidden="true" />
          ) : (
            <Upload aria-hidden="true" />
          )}
          <span>
            <strong>{file ? file.name : "Escolha um áudio ou vídeo"}</strong>
            <small>
              {file
                ? "Clique para trocar o arquivo"
                : "MKV, MP4, WAV, MP3 e outros formatos do FFmpeg"}
            </small>
          </span>
          {file && (
            <button
              type="button"
              className="icon-button"
              aria-label="Remover arquivo selecionado"
              title="Remover arquivo selecionado"
              onClick={(event) => {
                event.preventDefault();
                selectFile(null);
                if (fileInputRef.current) fileInputRef.current.value = "";
              }}
            >
              <X aria-hidden="true" />
            </button>
          )}
        </label>

        <div className="form-grid">
          <label>
            <span>Título</span>
            <input
              value={title}
              maxLength={240}
              placeholder="Ex.: Reunião semanal — 14 de julho"
              onChange={(event) => setTitle(event.currentTarget.value)}
            />
          </label>
          <label>
            <span>Número de falantes (opcional)</span>
            <div className="input-with-icon">
              <Users aria-hidden="true" />
              <input
                type="number"
                min="1"
                max="20"
                inputMode="numeric"
                placeholder="Automático"
                value={speakerCount}
                disabled={defaultDiarizationMode === "off"}
                onChange={(event) => setSpeakerCount(event.currentTarget.value)}
              />
            </div>
          </label>
          <button
            className="primary-button"
            type="submit"
            disabled={isSubmitting}
          >
            {isSubmitting ? "Enviando…" : "Enviar para transcrição"}
          </button>
        </div>
        {isSubmitting && (
          <div className="upload-progress" role="status" aria-live="polite">
            <div>
              <span style={{ width: `${Math.round(uploadProgress * 100)}%` }} />
            </div>
            <strong>{Math.round(uploadProgress * 100)}%</strong>
            {onCancel && (
              <button type="button" onClick={onCancel}>
                Cancelar envio
              </button>
            )}
          </div>
        )}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}
