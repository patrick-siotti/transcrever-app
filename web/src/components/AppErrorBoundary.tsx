import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State { failed: boolean }

export class AppErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled interface error', error, info.componentStack)
  }

  render() {
    if (this.state.failed) {
      return <main className="fatal-state"><span aria-hidden="true">!</span><h1>A interface encontrou um erro</h1><p>Seus arquivos permanecem seguros neste computador. Recarregue a página para tentar novamente.</p><button className="primary-button" type="button" onClick={() => window.location.reload()}>Recarregar aplicação</button></main>
    }
    return this.props.children
  }
}
