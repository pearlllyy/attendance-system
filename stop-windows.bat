@echo off
setlocal

where podman >nul 2>nul
if errorlevel 1 (
    echo Podman was not found in PATH.
    pause
    exit /b 1
)

podman rm -f attendance-app attendance-db >nul 2>nul

call :cleanup_lan_access

echo Attendance system containers stopped.
timeout /t 3 /nobreak >nul
exit /b 0

:cleanup_lan_access
fltmc >nul 2>&1
if errorlevel 1 goto cleanup_lan_access_elevated

netsh interface portproxy delete v4tov4 listenport=5000 listenaddress=0.0.0.0 >nul 2>nul
netsh advfirewall firewall delete rule name="Attendance System Port 5000" >nul 2>nul
exit /b 0

:cleanup_lan_access_elevated
set "CLEANUP_SCRIPT=%TEMP%\attendance-lan-cleanup.bat"
(
    echo @echo off
    echo netsh interface portproxy delete v4tov4 listenport=5000 listenaddress=0.0.0.0
    echo netsh advfirewall firewall delete rule name="Attendance System Port 5000"
) > "%CLEANUP_SCRIPT%"
powershell -NoProfile -Command "Start-Process -FilePath '%CLEANUP_SCRIPT%' -Verb RunAs -Wait" >nul 2>nul
del "%CLEANUP_SCRIPT%" >nul 2>nul
exit /b 0
