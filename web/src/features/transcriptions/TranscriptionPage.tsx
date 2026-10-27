import { useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Clock3, FolderOpen, LoaderCircle } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'

import { AppHeader } from '../../components/AppHeader'
import { getTranscription, getTranscriptionResult, mutateTranscription } from '../../lib/api'
import { formatDuration } from '../../lib/format'

const ACTIVE_STATES = new Set([
  'queued', 'preparing', 'loading_model', 'transcribing', 'diarizing', 'aligning', 'exporting',
  'cancel_requested',
])

export function TranscriptionPage() {
  const { transcriptionId = '' } = useParams()
  const item = useQuery({
    queryKey: ['transcription', transcriptionId],
    queryFn: () => getTranscription(transcriptionId),
    enabled: Boolean(transcriptionId),
    refetchInterval: (query) => ACTIVE_STATES.has(query.state.data?.status ?? '') ? 1000 : false,
  })
  const completed = item.data?.status.startsWith('completed') ?? false
  const result = useQuery({
    queryKey: ['transcription-result', transcriptionId],
    queryFn: () => getTranscriptionResult(transcriptionId),
    enabled: completed,
  })
  const openFolder = useMutation({
    mutationFn: () => mutateTranscription(transcriptionId, 'open-folder'),
    onSuccess: () => toast.success('Pasta aberta no computador.'),
    onError: (error: Error) => toast.error(error.message),
  })

  useEffect(() => {
    if (completed) {
      void mutateTranscription(transcriptionId, 'mark-viewed').catch(() => undefined)
    }
  }, [completed, transcriptionId])

  return (
    <div className="app-shell">
      <AppHeader />
      <main className="detail-main">
        <Link className="back-link" to="/"><ArrowLeft aria-hidden="true" /> Voltar à biblioteca</Link>
        {item.isLoading && <div className="state-panel"><LoaderCircle className="spin" aria-hidden="true" /><h2>Carregando transcrição</h2></div>}
        {item.isError && <div className="state-panel error-state"><h2>Não foi possível abrir esta transcrição</h2><p>Ela pode ter sido movida para a lixeira ou o aplicativo local está indisponível.</p></div>}
        {item.data && (
          <>
            <header className="detail-header">
              <div><h1>{item.data.title}</h1><p>{item.data.original_filename} · {formatDuration(item.data.duration_seconds)}</p></div>
              <button className="primary-button" type="button" disabled={!completed || openFolder.isPending} onClick={() => openFolder.mutate()}><FolderOpen aria-hidden="true" /> Abrir pasta</button>
            </header>
            {!completed && (
              <div className="state-panel detail-state">
                {ACTIVE_STATES.has(item.data.status) ? <LoaderCircle className="spin" aria-hidden="true" /> : <Clock3 aria-hidden="true" />}
                <h2>{item.data.status === 'failed' ? 'O processamento falhou' : 'Processamento em andamento'}</h2>
                <p>{item.data.error_message ?? 'O resultado aparecerá aqui assim que todos os arquivos forem gravados.'}</p>
                {ACTIVE_STATES.has(item.data.status) && <div className="detail-progress"><span style={{ width: `${Math.max(2, item.data.progress * 100)}%` }} /></div>}
              </div>
            )}
            {completed && result.isLoading && <div className="skeleton-list"><span /><span /><span /></div>}
            {completed && result.isError && <div className="state-panel error-state"><h2>O resultado não pôde ser lido</h2><p>Os metadados existem, mas o artefato pode estar ausente ou inválido.</p><button className="secondary-button" type="button" onClick={() => void result.refetch()}>Tentar novamente</button></div>}
            {completed && result.data && (
              <section className="transcript-surface" aria-labelledby="transcript-title">
                <div className="section-heading"><div><h2 id="transcript-title">Texto</h2><p>{result.data.segments.length} segmentos · {result.data.speakers.length} falantes</p></div></div>
                {result.data.segments.length === 0 ? <div className="state-panel"><h3>Nenhuma fala foi detectada</h3><p>O arquivo foi processado, mas não contém segmentos de voz reconhecidos.</p></div> : <div className="segments">{result.data.segments.map((segment, index) => <article className="segment" key={`${segment.start}-${index}`}><time>{formatDuration(segment.start)}</time><div><strong>{segment.speaker ?? 'Sem falante identificado'}</strong><p>{segment.text}</p></div></article>)}</div>}
              </section>
            )}
          </>
        )}
      </main>
    </div>
  )
}
