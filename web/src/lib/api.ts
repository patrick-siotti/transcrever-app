export interface Transcription {
  id: string
  folder_id: string | null
  title: string
  original_filename: string
  status: string
  stage: string | null
  progress: number
  processed_seconds: number | null
  duration_seconds: number | null
  model_name: string
  diarization_mode: string
  speaker_count: number | null
  is_pinned: boolean
  position: number
  viewed_at: string | null
  started_at?: string | null
  attempt_count: number
  error_code: string | null
  error_message: string | null
  warning_message: string | null
  created_at: string
  updated_at: string
}

export interface LibraryResponse {
  folder: Folder | null
  breadcrumbs: Folder[]
  folders: Folder[]
  new_transcriptions: Transcription[]
  transcriptions: Transcription[]
}

export interface Folder {
  id: string
  parent_id: string | null
  name: string
  is_pinned: boolean
  position: number
  created_at: string
  updated_at: string
}

export interface FolderTreeItem extends Folder {
  path: string
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
  speaker: string | null
}

export interface TranscriptionResult {
  job_id: string
  duration_seconds: number
  segments: TranscriptSegment[]
  speakers: string[]
  mode: string
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = 'Não foi possível concluir a operação.'
    try {
      const payload = (await response.json()) as { detail?: string; message?: string }
      message = payload.message ?? payload.detail ?? message
    } catch {
      // A mensagem segura acima é mantida quando a resposta não é JSON.
    }
    throw new ApiError(message, response.status)
  }
  return (await response.json()) as T
}

export async function getLibrary(folderId?: string): Promise<LibraryResponse> {
  const query = folderId ? `?folder_id=${encodeURIComponent(folderId)}` : ''
  return parseResponse<LibraryResponse>(await fetch(`/api/v1/library${query}`))
}

export async function getTranscription(id: string): Promise<Transcription> {
  return parseResponse<Transcription>(await fetch(`/api/v1/transcriptions/${encodeURIComponent(id)}`))
}

export async function getTranscriptionResult(id: string): Promise<TranscriptionResult> {
  return parseResponse<TranscriptionResult>(
    await fetch(`/api/v1/transcriptions/${encodeURIComponent(id)}/result`),
  )
}

export async function mutateTranscription(
  id: string,
  action: 'cancel' | 'retry' | 'mark-viewed' | 'open-folder',
): Promise<Transcription | null> {
  const response = await fetch(`/api/v1/transcriptions/${encodeURIComponent(id)}/${action}`, {
    method: 'POST',
  })
  if (response.status === 204) return null
  return parseResponse<Transcription>(response)
}

export async function patchTranscription(
  id: string,
  patch: Partial<Pick<Transcription, 'title' | 'is_pinned' | 'folder_id' | 'position'>>,
): Promise<Transcription> {
  return parseResponse<Transcription>(
    await fetch(`/api/v1/transcriptions/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }),
  )
}

export async function deleteTranscription(id: string): Promise<void> {
  const response = await fetch(`/api/v1/transcriptions/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (!response.ok) await parseResponse<never>(response)
}

export async function getTrash(): Promise<Transcription[]> {
  return parseResponse<Transcription[]>(await fetch('/api/v1/trash'))
}

export async function restoreTranscription(id: string): Promise<Transcription> {
  return parseResponse<Transcription>(
    await fetch(`/api/v1/transcriptions/${encodeURIComponent(id)}/restore`, { method: 'POST' }),
  )
}

export async function permanentlyDeleteTranscription(id: string): Promise<void> {
  const response = await fetch(`/api/v1/trash/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (!response.ok) await parseResponse<never>(response)
}

export async function createFolder(name: string, parentId: string | null): Promise<Folder> {
  return parseResponse<Folder>(
    await fetch('/api/v1/folders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, parent_id: parentId }),
    }),
  )
}

export async function getFolderTree(): Promise<FolderTreeItem[]> {
  return parseResponse<FolderTreeItem[]>(await fetch('/api/v1/folders/tree'))
}

export async function patchFolder(
  id: string,
  patch: Partial<Pick<Folder, 'name' | 'is_pinned' | 'position'>>,
): Promise<Folder> {
  return parseResponse<Folder>(
    await fetch(`/api/v1/folders/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }),
  )
}

export async function deleteFolder(id: string): Promise<void> {
  const response = await fetch(`/api/v1/folders/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (!response.ok) await parseResponse<never>(response)
}

export interface UploadInput {
  file: File
  title: string
  modelName: string
  diarizationMode: 'off' | 'auto' | 'pyannote' | 'clustering'
  speakerCount?: number
}

export function uploadTranscription(
  input: UploadInput,
  options: { onProgress?: (progress: number) => void; signal?: AbortSignal } = {},
): Promise<Transcription> {
  const form = new FormData()
  form.set('file', input.file)
  form.set('title', input.title)
  form.set('model_name', input.modelName)
  form.set('diarization_mode', input.diarizationMode)
  if (input.speakerCount !== undefined) {
    form.set('speaker_count', String(input.speakerCount))
  }
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('POST', '/api/v1/transcriptions')
    request.responseType = 'json'
    request.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) options.onProgress?.(event.loaded / event.total)
    })
    request.addEventListener('load', () => {
      if (request.status >= 200 && request.status < 300) {
        options.onProgress?.(1)
        resolve(request.response as Transcription)
        return
      }
      const payload = request.response as { detail?: string; message?: string } | null
      reject(new ApiError(payload?.message ?? payload?.detail ?? 'Não foi possível enviar o arquivo.', request.status))
    })
    request.addEventListener('error', () => reject(new ApiError('A conexão local foi interrompida durante o envio.', 0)))
    request.addEventListener('abort', () => reject(new DOMException('Envio cancelado.', 'AbortError')))
    options.signal?.addEventListener('abort', () => request.abort(), { once: true })
    request.send(form)
  })
}

export interface Preferences {
  default_model: string
  default_diarization_mode: 'off' | 'auto' | 'pyannote' | 'clustering'
  pyannote_configured: boolean
}

export interface Diagnostics {
  version: string
  database_path: string
  runs_path: string
  trash_path: string
  log_path: string
  worker_enabled: boolean
  maintenance: { interrupted: number; imported: number; missing_roots: number; invalid_runs: number; removed_partials: number }
}

export async function getPreferences(): Promise<Preferences> {
  return parseResponse<Preferences>(await fetch('/api/v1/system/preferences'))
}

export async function putPreferences(preferences: Omit<Preferences, 'pyannote_configured'>): Promise<Preferences> {
  return parseResponse<Preferences>(await fetch('/api/v1/system/preferences', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(preferences),
  }))
}

export async function getDiagnostics(): Promise<Diagnostics> {
  return parseResponse<Diagnostics>(await fetch('/api/v1/system/diagnostics'))
}
