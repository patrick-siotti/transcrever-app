# Transcrever App

Aplicativo para Windows que transcreve áudio e vídeo, separa falantes e organiza os resultados. Exporta textos e legendas em TXT, JSON, SRT e VTT.

## Instalar

Requer Git, Python 3.12 e uv.

Instale o FFmpeg e o FFprobe:

```powershell
winget install --id Gyan.FFmpeg --exact --source winget
```

Reabra o terminal e instale o aplicativo:

```powershell
git clone https://github.com/patrick-siotti/transcrever-app.git
cd transcrever-app
uv sync --frozen
```

## Usar

```powershell
uv run transcrever desktop
```

## Licença

[MIT](LICENSE) — Patrick G. Siotti.
