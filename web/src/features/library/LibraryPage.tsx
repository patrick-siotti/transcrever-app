import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronRight,
  FolderOpen,
  FolderPlus,
  Pencil,
  Pin,
  Trash2,
} from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { AppHeader } from "../../components/AppHeader";
import {
  createFolder,
  deleteFolder,
  deleteTranscription,
  getFolderTree,
  getPreferences,
  getLibrary,
  mutateTranscription,
  patchFolder,
  patchTranscription,
  restoreTranscription,
  uploadTranscription,
  type Transcription,
  type UploadInput,
  type LibraryResponse,
} from "../../lib/api";
import { CreateFolderDialog } from "../folders/CreateFolderDialog";
import { FolderCard } from "../folders/FolderCard";
import { MoveTranscriptionDialog } from "../folders/MoveTranscriptionDialog";
import { ManageFolderDialog } from "../folders/ManageFolderDialog";
import { UploadPanel } from "../upload/UploadPanel";
import { TranscriptionRow } from "./TranscriptionRow";

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

type RowAction = "cancel" | "retry" | "pin" | "open-folder" | "delete";
type VisibleRowAction = RowAction | "move";

export function LibraryPage() {
  const { folderId } = useParams<{ folderId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [folderDialogOpen, setFolderDialogOpen] = useState(false);
  const [pendingItem, setPendingItem] = useState<string>();
  const [moveItem, setMoveItem] = useState<Transcription>();
  const [folderManagement, setFolderManagement] = useState<
    "rename" | "delete"
  >();
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadController, setUploadController] = useState<AbortController>();
  const [uploadResetKey, setUploadResetKey] = useState(0);
  const libraryKey = ["library", folderId ?? null];
  const library = useQuery({
    queryKey: libraryKey,
    queryFn: () => getLibrary(folderId),
    refetchInterval: 1000,
  });
  const folderTree = useQuery({
    queryKey: ["folder-tree"],
    queryFn: getFolderTree,
    refetchInterval: 1000,
  });
  const preferences = useQuery({
    queryKey: ["preferences"],
    queryFn: getPreferences,
  });
  const upload = useMutation({
    mutationFn: (input: UploadInput) => {
      const controller = new AbortController();
      setUploadController(controller);
      setUploadProgress(0);
      return uploadTranscription(input, {
        signal: controller.signal,
        onProgress: setUploadProgress,
      });
    },
    onSuccess: async () => {
      setUploadResetKey((current) => current + 1);
      setUploadProgress(0);
      toast.success("Arquivo enviado e adicionado à fila.");
      await queryClient.invalidateQueries({ queryKey: ["library"] });
    },
    onError: (error: Error) =>
      error.name === "AbortError"
        ? toast.info("Envio cancelado.")
        : toast.error(error.message),
    onSettled: () => setUploadController(undefined),
  });
  const addFolder = useMutation({
    mutationFn: (name: string) => createFolder(name, folderId ?? null),
    onSuccess: async () => {
      setFolderDialogOpen(false);
      toast.success("Pasta criada.");
      await queryClient.invalidateQueries({ queryKey: libraryKey });
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const rowAction = useMutation({
    mutationFn: async ({
      item,
      action,
    }: {
      item: Transcription;
      action: RowAction;
    }) => {
      setPendingItem(item.id);
      if (action === "delete") return deleteTranscription(item.id);
      if (action === "pin")
        return patchTranscription(item.id, { is_pinned: !item.is_pinned });
      return mutateTranscription(item.id, action);
    },
    onSuccess: async (_, variables) => {
      const messages: Record<RowAction, string> = {
        cancel: "Cancelamento solicitado.",
        retry: "Transcrição adicionada novamente à fila.",
        pin: variables.item.is_pinned
          ? "Transcrição desafixada."
          : "Transcrição fixada.",
        "open-folder": "Pasta aberta.",
        delete: "Transcrição movida para a lixeira.",
      };
      if (variables.action === "delete") {
        toast.success(messages.delete, {
          duration: 8000,
          action: {
            label: "Desfazer",
            onClick: () => {
              void restoreTranscription(variables.item.id)
                .then(() =>
                  queryClient.invalidateQueries({ queryKey: ["library"] }),
                )
                .then(() => toast.success("Transcrição restaurada."))
                .catch((error: Error) => toast.error(error.message));
            },
          },
        });
      } else {
        toast.success(messages[variables.action]);
      }
      await queryClient.invalidateQueries({ queryKey: ["library"] });
    },
    onMutate: async ({ item, action }) => {
      if (action !== "pin") return undefined;
      await queryClient.cancelQueries({ queryKey: ["library"] });
      const snapshots = queryClient.getQueriesData<LibraryResponse>({
        queryKey: ["library"],
      });
      queryClient.setQueriesData<LibraryResponse>(
        { queryKey: ["library"] },
        (current) =>
          current
            ? {
                ...current,
                transcriptions: current.transcriptions.map((candidate) =>
                  candidate.id === item.id
                    ? { ...candidate, is_pinned: !candidate.is_pinned }
                    : candidate,
                ),
              }
            : current,
      );
      return { snapshots };
    },
    onError: (error: Error, _variables, context) => {
      context?.snapshots.forEach(([key, value]) =>
        queryClient.setQueryData(key, value),
      );
      toast.error(error.message);
    },
    onSettled: () => setPendingItem(undefined),
  });
  const moveTranscription = useMutation({
    mutationFn: ({
      item,
      targetFolderId,
    }: {
      item: Transcription;
      targetFolderId: string | null;
    }) => patchTranscription(item.id, { folder_id: targetFolderId }),
    onSuccess: async () => {
      setMoveItem(undefined);
      toast.success("Transcrição movida.");
      await queryClient.invalidateQueries({ queryKey: ["library"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const manageFolder = useMutation({
    mutationFn: async ({
      action,
      name,
    }: {
      action: "rename" | "delete" | "pin";
      name?: string;
    }) => {
      if (!folderId || !library.data?.folder) return;
      if (action === "delete") return deleteFolder(folderId);
      if (action === "pin")
        return patchFolder(folderId, {
          is_pinned: !library.data.folder.is_pinned,
        });
      if (!name) throw new Error("Informe um nome para a pasta.");
      return patchFolder(folderId, { name });
    },
    onSuccess: async (_, variables) => {
      setFolderManagement(undefined);
      if (variables.action === "delete") {
        toast.success("Pasta e conteúdo movidos para a lixeira.");
        await navigate("/");
      } else {
        toast.success(
          variables.action === "pin"
            ? "Fixação da pasta atualizada."
            : "Pasta renomeada.",
        );
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["library"] }),
        queryClient.invalidateQueries({ queryKey: ["folder-tree"] }),
      ]);
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const reorderFolder = useMutation({
    mutationFn: async ({
      folder,
      direction,
    }: {
      folder: (typeof folders)[number];
      direction: -1 | 1;
    }) => {
      const currentIndex = folders.findIndex(
        (candidate) => candidate.id === folder.id,
      );
      const target = folders[currentIndex + direction];
      if (!target || target.is_pinned !== folder.is_pinned) return;
      await Promise.all([
        patchFolder(folder.id, { position: currentIndex + direction }),
        patchFolder(target.id, { position: currentIndex }),
      ]);
    },
    onSuccess: async () =>
      queryClient.invalidateQueries({ queryKey: libraryKey }),
    onError: (error: Error) => toast.error(error.message),
  });
  const pinFolder = useMutation({
    mutationFn: (folder: (typeof folders)[number]) =>
      patchFolder(folder.id, { is_pinned: !folder.is_pinned }),
    onMutate: async (folder) => {
      await queryClient.cancelQueries({ queryKey: libraryKey });
      const snapshot = queryClient.getQueryData<LibraryResponse>(libraryKey);
      queryClient.setQueryData<LibraryResponse>(libraryKey, (current) =>
        current
          ? {
              ...current,
              folders: current.folders.map((candidate) =>
                candidate.id === folder.id
                  ? { ...candidate, is_pinned: !candidate.is_pinned }
                  : candidate,
              ),
            }
          : current,
      );
      return { snapshot };
    },
    onSuccess: async () =>
      queryClient.invalidateQueries({ queryKey: libraryKey }),
    onError: (error: Error, _folder, context) => {
      queryClient.setQueryData(libraryKey, context?.snapshot);
      toast.error(error.message);
    },
  });
  const reorderTranscription = useMutation({
    mutationFn: async ({
      item,
      direction,
    }: {
      item: Transcription;
      direction: -1 | 1;
    }) => {
      const currentIndex = items.findIndex(
        (candidate) => candidate.id === item.id,
      );
      const target = items[currentIndex + direction];
      if (!target || target.is_pinned !== item.is_pinned) return;
      await Promise.all([
        patchTranscription(item.id, { position: currentIndex + direction }),
        patchTranscription(target.id, { position: currentIndex }),
      ]);
    },
    onSuccess: async () =>
      queryClient.invalidateQueries({ queryKey: libraryKey }),
    onError: (error: Error) => toast.error(error.message),
  });

  function handleRowAction(item: Transcription, action: VisibleRowAction) {
    if (action === "move") {
      setMoveItem(item);
      return;
    }
    rowAction.mutate({ item, action });
  }

  function handleDropTranscription(
    transcriptionId: string,
    targetFolderId: string,
  ) {
    const item = items.find((candidate) => candidate.id === transcriptionId);
    if (item) moveTranscription.mutate({ item, targetFolderId });
  }

  const items = library.data?.transcriptions ?? [];
  const folders = library.data?.folders ?? [];
  const activeCount = items.filter((item) =>
    ACTIVE_STATES.has(item.status),
  ).length;

  return (
    <div className="app-shell">
      <AppHeader />
      <main>
        {folderId && (
          <nav className="breadcrumbs" aria-label="Localização">
            <Link to="/">Biblioteca</Link>
            {library.data?.breadcrumbs.slice(0, -1).map((folder) => (
              <span key={folder.id}>
                <ChevronRight aria-hidden="true" />
                <Link to={`/folders/${folder.id}`}>{folder.name}</Link>
              </span>
            ))}
          </nav>
        )}
        <div className="page-heading">
          <div>
            <h1>{library.data?.folder?.name ?? "Biblioteca"}</h1>
          </div>
          <div className="heading-actions">
            {folderId && library.data?.folder && (
              <>
                <button
                  className="icon-action"
                  type="button"
                  aria-label={
                    library.data.folder.is_pinned
                      ? "Desafixar pasta"
                      : "Fixar pasta"
                  }
                  title={
                    library.data.folder.is_pinned
                      ? "Desafixar pasta"
                      : "Fixar pasta"
                  }
                  onClick={() => manageFolder.mutate({ action: "pin" })}
                >
                  <Pin aria-hidden="true" />
                </button>
                <button
                  className="icon-action"
                  type="button"
                  aria-label="Renomear pasta"
                  title="Renomear pasta"
                  onClick={() => setFolderManagement("rename")}
                >
                  <Pencil aria-hidden="true" />
                </button>
                <button
                  className="icon-action danger-action"
                  type="button"
                  aria-label="Excluir pasta"
                  title="Excluir pasta"
                  onClick={() => setFolderManagement("delete")}
                >
                  <Trash2 aria-hidden="true" />
                </button>
              </>
            )}
            {activeCount > 0 && (
              <div className="active-summary">
                <span /> {activeCount} em andamento
              </div>
            )}
          </div>
        </div>

        <UploadPanel
          key={`${preferences.data?.default_model}-${preferences.data?.default_diarization_mode}-${uploadResetKey}`}
          isSubmitting={upload.isPending}
          defaultModel={preferences.data?.default_model}
          defaultDiarizationMode={preferences.data?.default_diarization_mode}
          uploadProgress={uploadProgress}
          onCancel={() => uploadController?.abort()}
          onSubmit={(input) => upload.mutate(input)}
        />

        <section
          className="library-section"
          aria-labelledby="library-title"
          aria-busy={library.isLoading}
        >
          <div className="section-heading">
            <div>
              <h2 id="library-title">Arquivos e pastas</h2>
              <p>
                {folders.length} pastas · {items.length} transcrições
              </p>
            </div>
            <div className="section-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => setFolderDialogOpen(true)}
              >
                <FolderPlus aria-hidden="true" /> Nova pasta
              </button>
            </div>
          </div>

          {library.isLoading && (
            <div className="skeleton-list" aria-label="Carregando biblioteca">
              <span />
              <span />
              <span />
            </div>
          )}
          {library.isError && (
            <div className="state-panel error-state">
              <span className="error-mark" aria-hidden="true">
                !
              </span>
              <h3>Não foi possível carregar a biblioteca</h3>
              <p>
                Confirme se o aplicativo local está aberto e tente novamente.
              </p>
              <button
                className="secondary-button"
                type="button"
                onClick={() => void library.refetch()}
              >
                Tentar novamente
              </button>
            </div>
          )}
          {folders.length > 0 && (
            <div className="folder-grid">
              {folders.map((folder, index) => (
                <FolderCard
                  key={folder.id}
                  folder={folder}
                  canMoveUp={
                    index > 0 &&
                    folders[index - 1]?.is_pinned === folder.is_pinned
                  }
                  canMoveDown={
                    index < folders.length - 1 &&
                    folders[index + 1]?.is_pinned === folder.is_pinned
                  }
                  onDropTranscription={handleDropTranscription}
                  onMove={(target, direction) =>
                    reorderFolder.mutate({ folder: target, direction })
                  }
                  onTogglePin={(target) => pinFolder.mutate(target)}
                />
              ))}
            </div>
          )}
          {!library.isLoading &&
            !library.isError &&
            folders.length === 0 &&
            items.length === 0 && (
              <div className="state-panel">
                <FolderOpen aria-hidden="true" />
                <h3>Nada por aqui ainda</h3>
                <p>Envie uma gravação ou crie uma pasta.</p>
              </div>
            )}
          {items.length > 0 && (
            <div className="transcription-list">
              {items.map((item, index) => (
                <TranscriptionRow
                  key={item.id}
                  item={item}
                  pendingAction={
                    pendingItem === item.id ? "pending" : undefined
                  }
                  canMoveUp={
                    index > 0 && items[index - 1]?.is_pinned === item.is_pinned
                  }
                  canMoveDown={
                    index < items.length - 1 &&
                    items[index + 1]?.is_pinned === item.is_pinned
                  }
                  onMove={(target, direction) =>
                    reorderTranscription.mutate({ item: target, direction })
                  }
                  onAction={handleRowAction}
                />
              ))}
            </div>
          )}
        </section>
      </main>
      <CreateFolderDialog
        open={folderDialogOpen}
        isSubmitting={addFolder.isPending}
        onClose={() => setFolderDialogOpen(false)}
        onSubmit={(name) => addFolder.mutate(name)}
      />
      <MoveTranscriptionDialog
        item={moveItem}
        folders={folderTree.data ?? []}
        isSubmitting={moveTranscription.isPending}
        onClose={() => setMoveItem(undefined)}
        onSubmit={(targetFolderId) => {
          if (moveItem)
            moveTranscription.mutate({ item: moveItem, targetFolderId });
        }}
      />
      <ManageFolderDialog
        folder={library.data?.folder ?? undefined}
        mode={folderManagement}
        isSubmitting={manageFolder.isPending}
        onClose={() => setFolderManagement(undefined)}
        onRename={(name) => manageFolder.mutate({ action: "rename", name })}
        onDelete={() => manageFolder.mutate({ action: "delete" })}
      />
    </div>
  );
}
