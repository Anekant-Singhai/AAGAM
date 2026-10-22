@echo off
rem Double-click to set up AAGAM. Extras: -ConfigureClaude -DesktopShortcut -LocalAI. It ends with `aagam doctor`.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1" %*
pause
