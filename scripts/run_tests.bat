@echo off
setlocal

set "ROOT_DIR=%~dp0.."
set "VENV_DIR=%ROOT_DIR%\.venv"

if not exist "%VENV_DIR%\Scripts\python.exe" (
  py -3 -m venv "%VENV_DIR%"
)

"%VENV_DIR%\Scripts\python.exe" -m pip install -r "%ROOT_DIR%\requirements.txt" pytest pytest-asyncio
"%VENV_DIR%\Scripts\python.exe" -m pytest -q %*

endlocal
