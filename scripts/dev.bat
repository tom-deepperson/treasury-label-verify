@echo off
REM Thin launcher: run server in PowerShell so cmd is not the parent of uvicorn.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1" -NoReload
exit /b 0
