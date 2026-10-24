@echo off
rem The AAGAM Manager: open, update, check, repair or remove AAGAM. The "AAGAM Manager" shortcut opens the same window.
rem manage.cmd -Text gives the same choices as a numbered menu in this console.
if /i "%~1"=="-Text" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\manage.ps1"
  exit /b %ERRORLEVEL%
)
start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\manager.ps1"
