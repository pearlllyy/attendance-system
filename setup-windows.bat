@echo off
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

where wsl >nul 2>nul
if errorlevel 1 goto install_wsl
wsl --status >nul 2>nul
if errorlevel 1 goto install_wsl

where podman >nul 2>nul
if errorlevel 1 goto install_podman

call "%PROJECT_DIR%launch-windows.bat"
exit /b %errorlevel%

:install_wsl
echo WSL2 is not ready on this machine.
echo Windows will ask for permission to install it.
echo After the installation finishes, restart Windows and run this file again.
powershell -NoProfile -Command "Start-Process -FilePath 'wsl.exe' -ArgumentList '--install' -Verb RunAs"
pause
exit /b 0

:install_podman
echo Podman is not installed yet.
echo Installing Podman with winget...
where winget >nul 2>nul
if errorlevel 1 (
    echo Winget is not available on this machine.
    echo Install the App Installer package from Microsoft, then run this file again.
    pause
    exit /b 1
)
winget install --id RedHat.Podman -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo Podman installation failed.
    echo Install Podman manually, then run this file again.
    pause
    exit /b 1
)

echo Podman was installed.
echo Run this file again to start the system.
pause
exit /b 0
