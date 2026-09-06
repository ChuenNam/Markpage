@echo off
rem ============================================================
rem  Markpage - build standalone Windows package one-click
rem  Output: releases\Markpage folder + Markpage.zip by assemble_release.py
rem          run Markpage.exe from either.
rem
rem  IMPORTANT: keep this file 100% ASCII and CRLF line endings.
rem  cmd.exe parses .bat as ANSI/GBK on Chinese Windows; any UTF-8
rem  Chinese comment/echo byte will swallow following ASCII chars
rem  and break every line. All Chinese naming is done in Python
rem  assemble_release.py, never in this file.
rem ============================================================
setlocal
cd /d "%~dp0"

rem ---- locate Python 3.11 (must ship tkinter) ----
set "PY311=%MARKPAGE_PY311%"
if not defined PY311 set "PY311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PY311%" set "PY311=C:\Program Files\Python311\python.exe"
if not exist "%PY311%" (
  echo [ERROR] Python 3.11 with tkinter not found.
  echo Set MARKPAGE_PY311 or install Python 3.11, then rerun.
  pause
  exit /b 1
)

rem ---- packaging venv created once under user profile ----
set "VDIR=%USERPROFILE%\.workbuddy\binaries\python\envs\docgui_pack"
set "VPY=%VDIR%\Scripts\python.exe"
if not exist "%VPY%" (
  echo [1/3] Creating packaging venv base Python 3.11 with tkinter...
  "%PY311%" -m venv "%VDIR%"
  if errorlevel 1 ( echo [ERROR] venv create failed. & pause & exit /b 1 )
)
echo [2/3] Ensuring deps markdown pygments pyinstaller...
"%VPY%" -m pip install --quiet --disable-pip-version-check markdown pygments pyinstaller
if errorlevel 1 ( echo [ERROR] pip install failed. & pause & exit /b 1 )

set "DIST=%~dp0dist"
set "WORK=%TEMP%\pyinstaller_work_markpage"
if exist "%DIST%" rmdir /s /q "%DIST%"

echo [3/3] PyInstaller building onedir ...
"%VPY%" -m PyInstaller --noconfirm --clean ^
  --distpath "%DIST%" --workpath "%WORK%" ^
  "%~dp0scripts\md_doc_gui.spec"
if errorlevel 1 ( echo [ERROR] PyInstaller failed. & pause & exit /b 1 )

echo [4/4] Assembling releases folder + zip ...
"%PY311%" "%~dp0scripts\assemble_release.py"
if errorlevel 1 ( echo [ERROR] assemble failed. & pause & exit /b 1 )

echo.
echo Done. See the releases folder (Markpage) and its zip.
echo Copy either one to any Windows PC and run Markpage.exe
endlocal
pause
