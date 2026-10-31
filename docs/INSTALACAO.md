# Instalação e modelos

[Transcrever App](../README.md) · Windows

## Dependências

Com Git e Python 3.12 instalados, execute no PowerShell:

```powershell
winget install --id astral-sh.uv --exact --source winget
winget install --id Gyan.FFmpeg --exact --source winget
winget install --id Microsoft.EdgeWebView2Runtime --exact --source winget
```

Esses pacotes fornecem o gerenciador de dependências Python, FFmpeg/FFprobe para leitura dos arquivos e WebView2 para a janela do aplicativo.

Reabra o terminal e instale o projeto:

```powershell
git clone https://github.com/patrick-siotti/transcrever-app.git
cd transcrever-app
uv sync --frozen
```

## Modelo de transcrição

Os modelos não acompanham o repositório nem são instalados pelo `uv sync`. O Whisper `large-v3`, padrão do aplicativo, é baixado automaticamente no primeiro processamento. Para baixar antes de abrir:

```powershell
uv run python -c "from faster_whisper.utils import download_model; download_model('large-v3')"
```

O download exige internet e fica no cache do Hugging Face. Small, Medium e Turbo podem ser escolhidos em **Configurações** e também são baixados quando utilizados pela primeira vez.

## Identificação de falantes com Pyannote

1. Aceite as condições de acesso do [modelo Community-1](https://huggingface.co/pyannote/speaker-diarization-community-1).
2. Crie um [token de leitura no Hugging Face](https://huggingface.co/settings/tokens).
3. Na pasta do projeto, crie a configuração:

```powershell
Copy-Item .env.example .env
notepad .env
```

Preencha `HF_TOKEN` com seu token, salve e abra o aplicativo. O modelo do Pyannote é baixado no primeiro uso.

Sem configurar Pyannote, selecione **Automática**, **Agrupamento local** ou **Desativada** em Configurações. O agrupamento local baixa o modelo SpeechBrain ECAPA no primeiro uso e o guarda em `models/`.

## GPU NVIDIA — opcional

A transcrição pode usar NVIDIA com driver compatível, cuBLAS do CUDA 12 e cuDNN 9 disponíveis. Siga as instruções da [documentação do faster-whisper](https://github.com/SYSTRAN/faster-whisper#gpu) para preparar essas bibliotecas.

Sem esse ambiente, o aplicativo pode transcrever pela CPU; GPU não é requisito para a instalação acima.

## Abrir

```powershell
uv run transcrever desktop
```

Selecione o arquivo em **Nova transcrição**, informe o título e inicie. O resultado fica na biblioteca para consulta e exportação.
