@echo off
rem Double-click to set up AAGAM in this folder. Extras: -ConfigureClaude -DesktopShortcut -LocalAI. It ends with `aagam doctor`.
rem (On a new computer, use install.cmd in the main folder instead: it does all of this and more.)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1" %*
pause
