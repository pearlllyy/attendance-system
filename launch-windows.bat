@echo off
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

where podman >nul 2>nul
if errorlevel 1 (
    echo Podman was not found in PATH.
    echo Install Podman first, then run this file again.
    pause
    exit /b 1
)

podman machine start >nul 2>nul
if errorlevel 1 (
    podman machine init --now
    if errorlevel 1 (
        echo Podman machine could not be started.
        pause
        exit /b 1
    )
)

podman network exists attendance-system-net >nul 2>nul
if errorlevel 1 (
    podman network create attendance-system-net
    if errorlevel 1 (
        echo Failed to create the Podman network.
        pause
        exit /b 1
    )
)

podman build -t attendance-system-app -f Containerfile .
if errorlevel 1 (
    echo Failed to build the app image.
    pause
    exit /b 1
)

podman run -d --replace --name db --network attendance-system-net -e MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=yes -e MARIADB_ROOT_HOST=%% -v attendance-db-data:/var/lib/mysql -v "%PROJECT_DIR%attendance-db.sql:/docker-entrypoint-initdb.d/attendance-db.sql:ro" docker.io/library/mariadb:11.4
if errorlevel 1 (
    echo Failed to start the database container.
    pause
    exit /b 1
)

podman run -d --replace --name attendance-app --network attendance-system-net -e MYSQL_HOST=db -p 5000:5000 -v "%PROJECT_DIR%:/app" attendance-system-app
if errorlevel 1 (
    echo Failed to start the app container.
    pause
    exit /b 1
)

start "" "https://localhost:5000"
echo Attendance system started.
echo Opened https://localhost:5000 in your browser.
pause
