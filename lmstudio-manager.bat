:: start-manager.bat
@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "lmstudio-manager.ps1"
pause