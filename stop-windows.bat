@echo off
setlocal

where podman >nul 2>nul
if errorlevel 1 (
    echo Podman was not found in PATH.
    pause
    exit /b 1
)

podman rm -f attendance-app attendance-db >nul 2>nul
echo Attendance system containers stopped.
timeout /t 3 /nobreak >nul
