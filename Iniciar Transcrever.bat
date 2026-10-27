@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo Erro: uv nao foi encontrado no PATH.
  pause
  exit /b 1
)
uv run transcrever desktop
if errorlevel 1 pause
endlocal
