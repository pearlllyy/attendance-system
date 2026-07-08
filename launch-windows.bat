@echo off
setlocal

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
podman run -d --name "%APP_CONTAINER%" --network "%NETWORK_NAME%" -e MYSQL_HOST=db -p 5000:5000 -v "%PROJECT_DIR%:/app" "%APP_IMAGE%"
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
start "" "%APP_URL%"
echo Attendance system started.
echo Opened %APP_URL% in your browser.
timeout /t 3 /nobreak >nul
