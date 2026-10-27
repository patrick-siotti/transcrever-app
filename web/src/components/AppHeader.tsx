import { AudioLines, Settings, ShieldCheck, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'

export function AppHeader() {
  return (
    <header className="topbar">
      <Link className="brand" to="/" aria-label="Transcrever — início">
        <span><AudioLines aria-hidden="true" /></span>
        <strong>Transcrever</strong>
      </Link>
      <div className="header-actions">
        <Link className="header-link" to="/trash"><Trash2 aria-hidden="true" /> Lixeira</Link>
        <Link className="header-link" to="/settings"><Settings aria-hidden="true" /> Configurações</Link>
        <div className="system-status"><ShieldCheck aria-hidden="true" /> Seus arquivos ficam neste computador</div>
      </div>
    </header>
  )
}
