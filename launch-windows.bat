@echo off
setlocal EnableDelayedExpansion

set "PROJECT_DIR=%~dp0"
set "NETWORK_NAME=attendance-system-net"
set "APP_IMAGE=attendance-system-app"
set "DB_CONTAINER=attendance-db"
set "APP_CONTAINER=attendance-app"
set "APP_URL=https://localhost:5000"

cd /d "%PROJECT_DIR%"

where podman >nul 2>nul
if errorlevel 1 (
    echo Podman was not found in PATH.
    echo Install Podman first, then run this file again.
    pause
    exit /b 1
)

podman info >nul 2>nul
if errorlevel 1 (
    podman machine start
    podman info >nul 2>nul
    if errorlevel 1 (
        podman machine init --now
        podman info >nul 2>nul
        if errorlevel 1 (
            echo Podman machine could not be started.
            pause
            exit /b 1
        )
    )
)

podman network exists "%NETWORK_NAME%" >nul 2>nul
if errorlevel 1 (
    podman network create "%NETWORK_NAME%"
    if errorlevel 1 (
        echo Failed to create the Podman network.
        pause
        exit /b 1
    )
)

echo Building the app image...
podman build -t "%APP_IMAGE%" -f Containerfile .
if errorlevel 1 (
    echo Failed to build the app image.
    pause
    exit /b 1
)

podman rm -f "%APP_CONTAINER%" "%DB_CONTAINER%" >nul 2>nul

echo Starting the database...
podman run -d --name "%DB_CONTAINER%" --network "%NETWORK_NAME%" --network-alias db -e MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=yes -e MARIADB_ROOT_HOST=%% -v attendance-db-data:/var/lib/mysql -v "%PROJECT_DIR%attendance-db.sql:/docker-entrypoint-initdb.d/attendance-db.sql:ro" docker.io/library/mariadb:11.4
if errorlevel 1 (
    echo Failed to start the database container.
    pause
    exit /b 1
)

echo Waiting for the database...
for /l %%i in (1,1,60) do (
    podman exec "%DB_CONTAINER%" mariadb-admin ping -h 127.0.0.1 --silent >nul 2>nul
    if not errorlevel 1 goto db_ready
    timeout /t 2 /nobreak >nul
)
echo Database did not become ready in time.
podman logs "%DB_CONTAINER%"
pause
exit /b 1

:db_ready
echo Starting the app...
podman run -d --name "%APP_CONTAINER%" --network "%NETWORK_NAME%" -e MYSQL_HOST=db -p 0.0.0.0:5000:5000 -v "%PROJECT_DIR%:/app" "%APP_IMAGE%"
if errorlevel 1 (
    echo Failed to start the app container.
    pause
    exit /b 1
)

echo Waiting for the app...
for /l %%i in (1,1,60) do (
    powershell -NoProfile -Command "$client = New-Object Net.Sockets.TcpClient; try { $client.Connect('127.0.0.1', 5000); $client.Close(); exit 0 } catch { exit 1 }" >nul 2>nul
    if not errorlevel 1 goto app_ready
    timeout /t 2 /nobreak >nul
)
echo App did not become ready in time.
podman logs "%APP_CONTAINER%"
pause
exit /b 1

:app_ready
call :setup_lan_access
if errorlevel 1 (
    echo.
    echo Warning: Mobile device access could not be configured.
    echo Click Yes when Windows asks for Administrator permission, then run launch-windows.bat again.
)

start "" "%APP_URL%"
echo.
echo Attendance system started.
echo.
echo On this computer:
echo   https://localhost:5000
echo.
echo On mobile devices (same Wi-Fi network):
powershell -NoProfile -Command "& { $ips = @(Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object { $_.IPEnabled -and $_.DefaultIPGateway } | ForEach-Object { $_.IPAddress } | Where-Object { $_ -match '^\d+\.' -and $_ -ne '127.0.0.1' -and $_ -notmatch '^169\.254\.' } | Sort-Object -Unique); if ($ips.Count -eq 0) { Write-Host '  Could not detect a network IP address.'; Write-Host '  Run ipconfig and open: https://YOUR_IP:5000/scanner' } else { foreach ($ip in $ips) { Write-Host ('  https://{0}:5000/scanner' -f $ip) } } }"
echo.
echo Your phone may warn about the security certificate the first time.
echo You can continue for local use.
echo.
echo Opened %APP_URL% in your browser.
echo Press any key to exit this window. The app will continue running in the background.
pause >nul
exit /b 0

:setup_lan_access
set "WSL_IP="
for /f "tokens=1" %%i in ('podman machine ssh hostname -I 2^>nul') do set "WSL_IP=%%i"
if not defined WSL_IP (
    for /f "tokens=1" %%i in ('wsl hostname -I 2^>nul') do set "WSL_IP=%%i"
)
if not defined WSL_IP exit /b 1

fltmc >nul 2>&1
if errorlevel 1 goto setup_lan_access_elevated

netsh interface portproxy delete v4tov4 listenport=5000 listenaddress=0.0.0.0 >nul 2>nul
netsh interface portproxy add v4tov4 listenport=5000 listenaddress=0.0.0.0 connectport=5000 connectaddress=%WSL_IP% >nul 2>nul
if errorlevel 1 exit /b 1

netsh advfirewall firewall delete rule name="Attendance System Port 5000" >nul 2>nul
netsh advfirewall firewall add rule name="Attendance System Port 5000" dir=in action=allow protocol=TCP localport=5000 >nul 2>nul
exit /b 0

:setup_lan_access_elevated
set "SETUP_SCRIPT=%TEMP%\attendance-lan-setup.bat"
(
    echo @echo off
    echo netsh interface portproxy delete v4tov4 listenport=5000 listenaddress=0.0.0.0
    echo netsh interface portproxy add v4tov4 listenport=5000 listenaddress=0.0.0.0 connectport=5000 connectaddress=%WSL_IP%
    echo netsh advfirewall firewall delete rule name="Attendance System Port 5000"
    echo netsh advfirewall firewall add rule name="Attendance System Port 5000" dir=in action=allow protocol=TCP localport=5000
) > "%SETUP_SCRIPT%"
echo.
echo Windows needs Administrator permission so phones can connect.
echo Click Yes on the security prompt.
powershell -NoProfile -Command "Start-Process -FilePath '%SETUP_SCRIPT%' -Verb RunAs -Wait"
set "SETUP_EXIT=!ERRORLEVEL!"
del "%SETUP_SCRIPT%" >nul 2>nul
if not "!SETUP_EXIT!"=="0" exit /b 1
exit /b 0