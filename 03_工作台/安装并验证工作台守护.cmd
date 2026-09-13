@echo off
setlocal
set "ROOT=%~dp0"
set "SCRIPT=%ROOT%install-workbench-watchdog.ps1"

rem This command intentionally opens a UAC prompt. Task Scheduler must create
rem the watchdog outside the Codex process tree, or Codex restarts will stop it.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File','%SCRIPT%')"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%verify-workbench-watchdog.ps1"
pause
