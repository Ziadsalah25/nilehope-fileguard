@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-LocalAgent.ps1" %*
exit /b %errorlevel%
