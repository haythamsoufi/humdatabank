@echo off
setlocal

REM Windows batch is only a launcher. The menu and Azure CLI logic live in
REM run-azure-loadtest.ps1 so control flow is reliable and errors stay visible.

set "SCRIPT=%~dp0run-azure-loadtest.ps1"

if not exist "%SCRIPT%" (
    echo [error] PowerShell runner not found:
    echo         %SCRIPT%
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [error] Azure load test runner exited with code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
