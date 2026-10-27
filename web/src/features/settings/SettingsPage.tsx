import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Database, FileClock, FolderCog, Save } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { AppHeader } from "../../components/AppHeader";
import {
  getDiagnostics,
  getPreferences,
  putPreferences,
  type Preferences,
} from "../../lib/api";

type PreferencesForm = Omit<Preferences, "pyannote_configured">;

export function SettingsPage() {
  const queryClient = useQueryClient();
  const preferences = useQuery({
    queryKey: ["preferences"],
    queryFn: getPreferences,
  });
  const diagnostics = useQuery({
    queryKey: ["diagnostics"],
    queryFn: getDiagnostics,
  });
  const [form, setForm] = useState<PreferencesForm>({
    default_model: "large-v3",
    default_diarization_mode: "pyannote",
  });
  useEffect(() => {
    if (preferences.data) {
      setForm({
        default_model: preferences.data.default_model,
        default_diarization_mode:
          preferences.data.default_diarization_mode === "pyannote" &&
          !preferences.data.pyannote_configured
            ? "auto"
            : preferences.data.default_diarization_mode,
      });
    }
  }, [preferences.data]);
  const save = useMutation({
    mutationFn: putPreferences,
    onSuccess: async (value) => {
      queryClient.setQueryData(["preferences"], value);
      toast.success("Preferências salvas.");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(form);
  }

  function changeModel(event: ChangeEvent<HTMLSelectElement>) {
    const value = event.currentTarget.value;
    setForm((current) => ({ ...current, default_model: value }));
  }

  function changeDiarizationMode(event: ChangeEvent<HTMLSelectElement>) {
    const value = event.currentTarget
      .value as PreferencesForm["default_diarization_mode"];
    setForm((current) => ({ ...current, default_diarization_mode: value }));
  }

  const report = diagnostics.data?.maintenance;
  return (
    <div className="app-shell">
      <AppHeader />
      <main className="settings-main">
        <Link className="back-link" to="/">
          <ArrowLeft aria-hidden="true" /> Voltar à biblioteca
        </Link>
        <div className="page-heading">
          <div>
            <h1>Configurações</h1>
          </div>
        </div>
        <div className="settings-layout">
          <section
            className="settings-section"
            aria-labelledby="defaults-title"
          >
            <div className="settings-title">
              <FolderCog aria-hidden="true" />
              <div>
                <h2 id="defaults-title">Padrões de transcrição</h2>
              </div>
            </div>
            <form onSubmit={submit} className="settings-form">
              <label>
                <span>Modelo padrão</span>
                <select value={form.default_model} onChange={changeModel}>
                  <option value="large-v3">Large v3 — melhor qualidade</option>
                  <option value="turbo">Turbo — mais rápido</option>
                  <option value="medium">Medium — equilibrado</option>
                  <option value="small">Small — econômico</option>
                </select>
              </label>
              <label>
                <span>Identificação de falantes</span>
                <select
                  aria-label="Identificação de falantes"
                  value={form.default_diarization_mode}
                  onChange={changeDiarizationMode}
                >
                  <option value="auto">Automática</option>
                  <option
                    value="pyannote"
                    disabled={!preferences.data?.pyannote_configured}
                  >
                    Pyannote
                    {preferences.data?.pyannote_configured
                      ? ""
                      : " — requer configuração"}
                  </option>
                  <option value="clustering">Agrupamento local</option>
                  <option value="off">Desativada</option>
                </select>
                {!preferences.data?.pyannote_configured && (
                  <small>
                    Configure HF_TOKEN ou HUGGINGFACE_TOKEN antes de usar Pyannote.
                  </small>
                )}
              </label>
              <button
                className="primary-button"
                type="submit"
                disabled={save.isPending || preferences.isLoading}
              >
                <Save aria-hidden="true" /> Salvar preferências
              </button>
            </form>
          </section>
          <section
            className="settings-section"
            aria-labelledby="diagnostics-title"
          >
            <div className="settings-title">
              <Database aria-hidden="true" />
              <div>
                <h2 id="diagnostics-title">Diagnóstico</h2>
              </div>
            </div>
            {diagnostics.isLoading && (
              <div className="skeleton-list">
                <span />
                <span />
              </div>
            )}
            {diagnostics.isError && (
              <div className="error-inline">
                Não foi possível carregar o diagnóstico.{" "}
                <button
                  type="button"
                  onClick={() => void diagnostics.refetch()}
                >
                  Tentar novamente
                </button>
              </div>
            )}
            {diagnostics.data && (
              <dl className="diagnostics-list">
                <div>
                  <dt>Versão</dt>
                  <dd>{diagnostics.data.version}</dd>
                </div>
                <div>
                  <dt>Banco de dados</dt>
                  <dd>{diagnostics.data.database_path}</dd>
                </div>
                <div>
                  <dt>Runs</dt>
                  <dd>{diagnostics.data.runs_path}</dd>
                </div>
                <div>
                  <dt>Lixeira</dt>
                  <dd>{diagnostics.data.trash_path}</dd>
                </div>
                <div>
                  <dt>Log</dt>
                  <dd>{diagnostics.data.log_path}</dd>
                </div>
                <div>
                  <dt>Worker</dt>
                  <dd>
                    {diagnostics.data.worker_enabled ? "Ativo" : "Desativado"}
                  </dd>
                </div>
              </dl>
            )}
          </section>
          {report && (
            <section
              className="maintenance-strip"
              aria-labelledby="maintenance-title"
            >
              <FileClock aria-hidden="true" />
              <div>
                <h2 id="maintenance-title">Última inicialização</h2>
                <p>
                  {report.imported} runs importados · {report.interrupted}{" "}
                  interrompidos recuperados · {report.missing_roots} pastas
                  ausentes · {report.invalid_runs} runs inválidos ·{" "}
                  {report.removed_partials} parciais removidos
                </p>
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
