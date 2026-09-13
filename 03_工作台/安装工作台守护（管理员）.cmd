@echo off
setlocal
set "SCRIPT=%~dp0install-workbench-watchdog.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File','%SCRIPT%')"
endlocal
