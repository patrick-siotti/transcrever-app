import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { LibraryPage } from './features/library/LibraryPage'
import { TranscriptionPage } from './features/transcriptions/TranscriptionPage'
import { TrashPage } from './features/trash/TrashPage'
import { SettingsPage } from './features/settings/SettingsPage'
import { AppErrorBoundary } from './components/AppErrorBoundary'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: true },
  },
})

export default function App() {
  return (
    <AppErrorBoundary><QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LibraryPage />} />
          <Route path="/folders/:folderId" element={<LibraryPage />} />
          <Route path="/transcriptions/:transcriptionId" element={<TranscriptionPage />} />
          <Route path="/trash" element={<TrashPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="bottom-right" richColors closeButton />
    </QueryClientProvider></AppErrorBoundary>
  )
}
