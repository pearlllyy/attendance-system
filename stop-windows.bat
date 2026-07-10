@echo off
setlocal

where podman >nul 2>nul
if errorlevel 1 (
    echo Podman was not found in PATH.
    pause
    exit /b 1
)

podman rm -f attendance-app attendance-db >nul 2>nul

netsh interface portproxy delete v4tov4 listenport=5000 listenaddress=0.0.0.0 >nul 2>nul
netsh advfirewall firewall delete rule name="Attendance System Port 5000" >nul 2>nul

echo Attendance system containers stopped.
timeout /t 3 /nobreak >nul
