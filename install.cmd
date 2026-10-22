@echo off
rem Installs AAGAM on this computer, with everything it needs: double-click this file.
rem It needs the rest of the AAGAM folder next to it (extract the ZIP first). Extras: -NoLocalAI -NoClaude -NoShortcuts.
setlocal
set "HERE=%~dp0"
if not exist "%HERE%scripts\install.ps1" (
  echo.
  echo   This file needs the rest of the AAGAM folder next to it.
  echo   If you opened it from inside the ZIP: close this window, right-click the ZIP,
  echo   choose "Extract All...", then open the extracted folder and double-click install.cmd there.
  echo.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%scripts\install.ps1" %*
set "CODE=%ERRORLEVEL%"
echo.
pause
exit /b %CODE%
