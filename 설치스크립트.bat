@echo off
chcp 65001 > nul
title Environment Installer
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_environment.ps1"
echo.
echo Press any key to close this window...
pause > nul
