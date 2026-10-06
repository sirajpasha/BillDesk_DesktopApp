@echo off
setlocal enabledelayedexpansion

:: ==============================================================================
:: BillDesk Native - Application Startup Script (Batch Launcher)
::
:: Checks and starts dependencies (MongoDB, Python, Packages) before
:: starting the application with: python main.py
:: ==============================================================================

title BillDesk Native ERP Launcher
cd /d "%~dp0"

:: Check if powershell is available to run comprehensive pre-flight & dependency checks
where powershell.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
    set EXIT_CODE=!ERRORLEVEL!
    if !EXIT_CODE! NEQ 0 (
        echo.
        echo [ERROR] Application or dependency setup exited with code !EXIT_CODE!.
        pause
    )
    exit /b !EXIT_CODE!
)

:: Fallback if PowerShell is unavailable: Native Batch Pre-flight
echo [INFO] Running pure batch dependency check...

:: 1. Check Python
where python.exe >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python was not found in PATH! Please install Python 3.10+.
    pause
    exit /b 1
)

:: 2. Check MongoDB Port 27018
netstat -ano | findstr /R /C:":27018 .*LISTENING" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] MongoDB is not running on port 27018. Starting MongoDB...
    set "DATA_DIR=%APPDATA%\BillDesk\db"
    set "LOG_DIR=%APPDATA%\BillDesk\logs"
    if not exist "!DATA_DIR!" mkdir "!DATA_DIR!"
    if not exist "!LOG_DIR!" mkdir "!LOG_DIR!"

    set "MONGOD_EXE=%~dp0resources\mongo\win32-x64\mongod.exe"
    if not exist "!MONGOD_EXE!" (
        where mongod >nul 2>&1
        if !ERRORLEVEL! EQU 0 for /f "delims=" %%I in ('where mongod') do set "MONGOD_EXE=%%I"
    )

    if exist "!MONGOD_EXE!" (
        start "" /b "!MONGOD_EXE!" --dbpath "!DATA_DIR!" --bind_ip 127.0.0.1 --port 27018 --logpath "!LOG_DIR!\mongod.log" --logappend --wiredTigerCacheSizeGB 0.5
        echo [INFO] Waiting for MongoDB to initialize...
        timeout /t 3 /nobreak >nul
    ) else (
        echo [ERROR] mongod.exe not found! Please ensure resources\mongo\win32-x64\mongod.exe exists.
        pause
        exit /b 1
    )
) else (
    echo [OK] MongoDB is running on port 27018.
)

:: 3. Launch Application
echo [INFO] Starting application: python main.py
python main.py %*
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% NEQ 0 (
    echo.
    echo [ERROR] Application exited with code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
