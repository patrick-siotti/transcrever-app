<br>

<h1 align="center">Transcrever App</h1>

<p align="center">
  Suas gravações em texto e legendas.
</p>

<br>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-30363D?style=for-the-badge" alt="Windows">
  &nbsp;&nbsp;
  <img src="https://img.shields.io/badge/Python%203.12-30363D?style=for-the-badge&amp;logo=python&amp;logoColor=white" alt="Python 3.12">
</p>

<br>

<p align="center">
  <a href="#instalação">Instalação</a>
  &nbsp; · &nbsp;
  <a href="#uso">Uso</a>
  &nbsp; · &nbsp;
  <a href="docs/INSTALACAO.md">Modelos e configuração</a>
</p>

<br>

## Sobre o projeto

Transforme reuniões, aulas, entrevistas e vídeos em transcrições organizadas. O Transcrever processa os arquivos no computador, em uma interface para Windows.

- Exporte texto e legendas em **TXT, JSON, SRT e VTT**.
- Separe as vozes com **Pyannote** ou agrupamento local.
- Organize os resultados em uma biblioteca com fila, pastas e lixeira.

<br>

## Instalação

Requer **Git** e **Python 3.12**. No PowerShell:

```powershell
winget install --id astral-sh.uv --exact --source winget
winget install --id Gyan.FFmpeg --exact --source winget
winget install --id Microsoft.EdgeWebView2Runtime --exact --source winget
```

Reabra o terminal e instale o aplicativo:

```powershell
git clone https://github.com/patrick-siotti/transcrever-app.git
cd transcrever-app
uv sync --frozen
```

**Modelos:** o Whisper `large-v3` é baixado no primeiro processamento e exige internet. Para usar Pyannote, aceite o acesso ao modelo e configure `HF_TOKEN` antes de abrir. O [guia de modelos e configuração](docs/INSTALACAO.md) traz os passos e o comando para antecipar o download.

<br>

## Uso

```powershell
uv run transcrever desktop
```

Escolha um áudio ou vídeo em **Nova transcrição**, informe o título e inicie. Consulte o resultado na biblioteca e exporte no formato desejado.

<br>

## Licença

Distribuído sob a [licença MIT](LICENSE). Autoria de **Patrick G. Siotti**.
