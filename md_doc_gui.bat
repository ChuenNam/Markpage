@echo off
rem MD Doc Site Generator - GUI launcher (dual-mode).
rem Tries pythonw first (no console); if it does not stay alive,
rem falls back to console python (proven to work on this machine).
rem NOTE: keep this file pure ASCII (cmd parses .bat as ANSI/GBK).
setlocal
cd /d "%~dp0"

set "PY="
set "PYW="
for %%P in (
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
  "C:\Python311\python.exe"
  "C:\Python310\python.exe"
) do if not defined PY if exist "%%~P" set "PY=%%~P"
for %%P in (
  "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
  "%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe"
  "C:\Python311\pythonw.exe"
  "C:\Python310\pythonw.exe"
) do if not defined PYW if exist "%%~P" set "PYW=%%~P"

if not defined PY (
  echo [ERROR] python.exe was not found. Install Python 3.10/3.11, then retry.
  pause
  exit /b 1
)

if defined PYW (
  start "" "%PYW%" "%~dp0md_doc_gui.py"
  rem give it a moment, then check it is really running
  timeout /t 2 /nobreak >nul
  tasklist /FI "IMAGENAME eq pythonw.exe" | findstr /i "pythonw.exe" >nul
  if errorlevel 1 (
    echo pythonw did not stay alive - retrying with console python.
    start "" "%PY%" "%~dp0md_doc_gui.py"
  )
) else (
  start "" "%PY%" "%~dp0md_doc_gui.py"
)
endlocal
