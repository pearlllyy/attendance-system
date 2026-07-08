@echo off
setlocal

where podman >nul 2>nul
if errorlevel 1 (
    echo Podman was not found in PATH.
    pause
    exit /b 1
)

podman stop attendance-app db >nul 2>nul
echo Attendance system containers stopped.
pause
