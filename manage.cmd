@echo off
rem The AAGAM Manager: open, update, check, repair or remove AAGAM. The "AAGAM Manager" shortcut opens this.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\manage.ps1" %*
