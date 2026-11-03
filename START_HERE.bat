@echo off
setlocal enabledelayedexpansion
title AgentSearch - Multi-Agent Search Engine
cd /d "%~dp0"

echo.
echo  ==========================================================
echo     AgentSearch  -  Multi-Agent Search Engine
echo     One-click launcher for Windows
echo  ==========================================================
echo.

REM ---------- 1. Locate Python ----------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo  [ERROR] Python was not found on this computer.
    echo.
    echo  Please install Python 3.10 or newer:
    echo     https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: tick "Add Python to PATH" during installation,
    echo  then double-click this file again.
    echo.
    pause
    exit /b 1
)

echo  [1/4] Python found.
%PY% --version
echo.

REM ---------- 2. Create virtual environment ----------
if not exist ".venv\Scripts\python.exe" (
    echo  [2/4] Creating virtual environment .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo.
        echo  [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo  [2/4] Virtual environment already exists - reusing it.
)
set "VPY=.venv\Scripts\python.exe"
echo.

REM ---------- 3. Install dependencies ----------
echo  [3/4] Installing dependencies...
echo        First run can take 1-3 minutes. Please wait.
echo.
"%VPY%" -m pip install --upgrade pip >nul 2>nul
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Dependency installation failed.
    echo  Check your internet connection and run this file again.
    echo.
    pause
    exit /b 1
)
echo.

REM ---------- 4. Read port and launch ----------
set "PORT=8000"
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /i "%%A"=="PORT" if not "%%B"=="" set "PORT=%%B"
    )
)

echo  [4/4] Starting AgentSearch server...
echo.
echo  ==========================================================
echo     App URL : http://localhost:%PORT%
echo     API docs: http://localhost:%PORT%/docs
echo.
echo     Your browser will open automatically.
echo     KEEP THIS WINDOW OPEN while using the app.
echo     Press Ctrl+C here to stop the server.
echo  ==========================================================
echo.

REM Open the browser after the server has had time to boot.
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 6; Start-Process 'http://localhost:%PORT%'" >nul 2>nul

"%VPY%" run.py

echo.
echo  Server stopped.
pause
endlocal
