import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RotateCcw, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { AppHeader } from "../../components/AppHeader";
import {
  getTrash,
  permanentlyDeleteTranscription,
  restoreTranscription,
  type Transcription,
} from "../../lib/api";
import { formatDate } from "../../lib/format";
import { useModalKeyboard } from "../../lib/useModalKeyboard";

type TrashAction = "restore" | "remove";

export function TrashPage() {
  const queryClient = useQueryClient();
  const [confirmation, setConfirmation] = useState<Transcription>();
  const confirmationRef = useRef<HTMLElement>(null);
  useModalKeyboard(Boolean(confirmation), confirmationRef, () =>
    setConfirmation(undefined),
  );
  const trash = useQuery({
    queryKey: ["trash"],
    queryFn: getTrash,
    refetchInterval: 1000,
  });
  const action = useMutation({
    mutationFn: async ({
      item,
      kind,
    }: {
      item: Transcription;
      kind: TrashAction;
    }) => {
      if (kind === "restore") {
        await restoreTranscription(item.id);
        return;
      }
      await permanentlyDeleteTranscription(item.id);
    },
    onMutate: async ({ item, kind }) => {
      await queryClient.cancelQueries({ queryKey: ["trash"] });
      const snapshot = queryClient.getQueryData<Transcription[]>(["trash"]);
      queryClient.setQueryData<Transcription[]>(["trash"], (current) =>
        current?.filter((candidate) => candidate.id !== item.id),
      );
      if (kind === "remove") setConfirmation(undefined);
      return { snapshot };
    },
    onSuccess: (_, variables) => {
      toast.success(
        variables.kind === "restore"
          ? "Transcrição restaurada."
          : "Item removido permanentemente.",
      );
    },
    onError: (error: Error, variables, context) => {
      queryClient.setQueryData(["trash"], context?.snapshot);
      if (variables.kind === "remove") setConfirmation(variables.item);
      toast.error(error.message);
    },
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["trash"] }),
        queryClient.invalidateQueries({ queryKey: ["library"] }),
      ]);
    },
  });

  const items = trash.data ?? [];
  return (
    <div className="app-shell">
      <AppHeader />
      <main>
        <Link className="back-link" to="/">
          <ArrowLeft aria-hidden="true" /> Voltar à biblioteca
        </Link>
        <div className="page-heading">
          <div>
            <h1>Lixeira</h1>
          </div>
        </div>
        <section className="library-section" aria-busy={trash.isLoading}>
          {trash.isLoading && (
            <div className="skeleton-list" aria-label="Carregando lixeira">
              <span />
              <span />
            </div>
          )}
          {trash.isError && (
            <div className="state-panel error-state">
              <h2>Não foi possível carregar a lixeira</h2>
              <button
                className="secondary-button"
                type="button"
                onClick={() => void trash.refetch()}
              >
                Tentar novamente
              </button>
            </div>
          )}
          {!trash.isLoading && !trash.isError && items.length === 0 && (
            <div className="state-panel">
              <Trash2 aria-hidden="true" />
              <h2>Nenhum item na lixeira</h2>
              <p>Transcrições excluídas podem ser restauradas aqui.</p>
            </div>
          )}
          {items.length > 0 && (
            <div className="trash-list">
              {items.map((item) => (
                <article className="trash-row" key={item.id}>
                  <div>
                    <strong>{item.title}</strong>
                    <span>
                      {item.original_filename} · excluída em{" "}
                      {formatDate(item.updated_at)}
                    </span>
                  </div>
                  <div>
                    <button
                      className="secondary-button"
                      type="button"
                      disabled={action.isPending}
                      onClick={() => action.mutate({ item, kind: "restore" })}
                    >
                      <RotateCcw aria-hidden="true" /> Restaurar
                    </button>
                    <button
                      className="danger-button"
                      type="button"
                      disabled={action.isPending}
                      onClick={() => setConfirmation(item)}
                    >
                      <Trash2 aria-hidden="true" /> Excluir definitivamente
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>
      {confirmation && (
        <div className="dialog-backdrop" role="presentation">
          <section
            ref={confirmationRef}
            className="dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-title"
            aria-describedby="delete-copy"
          >
            <div className="dialog-heading">
              <span>
                <Trash2 aria-hidden="true" />
              </span>
              <div>
                <h2 id="delete-title">Excluir definitivamente?</h2>
                <p id="delete-copy">
                  Todos os arquivos de “{confirmation.title}” serão removidos.
                  Esta ação não pode ser desfeita.
                </p>
              </div>
            </div>
            <div className="dialog-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => setConfirmation(undefined)}
              >
                Cancelar
              </button>
              <button
                className="danger-button"
                type="button"
                disabled={action.isPending}
                onClick={() =>
                  action.mutate({ item: confirmation, kind: "remove" })
                }
              >
                Excluir definitivamente
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
