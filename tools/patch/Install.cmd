@echo off
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0Entry.ps1" -Action Install -GameDir "%~1"
echo.
echo Press any key to close...
pause >nul
