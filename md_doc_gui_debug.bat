@echo off
rem MD Doc Site GUI - DIAGNOSTIC launcher (console visible, shows errors).
rem Pure ASCII only (cmd parses .bat as ANSI/GBK).
setlocal
cd /d "%~dp0"

echo ============================================================
echo  MD Doc Site Generator - diagnostic launcher
echo ============================================================
set "PY="
for %%P in (
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
  "C:\Python311\python.exe"
  "C:\Python310\python.exe"
) do if exist "%%~P" set "PY=%%~P"

if not defined PY (
  echo [ERROR] python.exe was not found in the usual locations.
  echo Install Python 3.10 / 3.11, then retry.
  pause
  exit /b 1
)
echo Python     : %PY%
"%PY%" -c "import sys; print('version     :', sys.version.split()[0])"
"%PY%" -c "import tkinter; print('tkinter     : OK')"
if errorlevel 1 (
  echo [ERROR] tkinter import failed - install Python with tcl/tk.
  pause
  exit /b 1
)
echo Launching GUI (keep this window open; errors appear here)...
echo ------------------------------------------------------------
"%PY%" "%~dp0md_doc_gui.py"
echo ------------------------------------------------------------
echo GUI exited with code %errorlevel%.
echo If nothing appeared above, check tools\gui_error.log.
pause
endlocal
