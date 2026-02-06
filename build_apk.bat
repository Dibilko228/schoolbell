@echo off
REM Build APK for Windows using WSL2
REM Requires: WSL2 with Ubuntu 20.04+

setlocal enabledelayedexpansion

echo.
echo SchoolBell APK Build (Windows)
echo ===============================
echo.
echo This script will:
echo  1. Check if WSL2 is installed
echo  2. Setup Android SDK/NDK in WSL2
echo  3. Build APK using buildozer
echo.

REM Check if wsl is available
wsl --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: WSL2 not found. Please install WSL2 first:
    echo   wsl --install
    exit /b 1
)

echo WSL2 found. Running build inside WSL...
echo.

REM Run build script inside WSL
wsl bash -c "cd /mnt/c/Users/%USERNAME%/Desktop/mommy && bash build_apk.sh"

if errorlevel 1 (
    echo Build failed!
    exit /b 1
)

echo.
echo Build successful!
echo APK: c:\Users\%USERNAME%\Desktop\mommy\android_port\bin\schoolbell-1.0-debug.apk
echo.
pause
