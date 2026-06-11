@echo off
setlocal enabledelayedexpansion
title Quick Data - Server Launcher
cls

echo =====================================================================
echo                    QUICK DATA - SERVER LAUNCHER                      
echo =====================================================================
echo(

REM 1. Check for Gemini API Key
set "API_KEY_FOUND=0"
if not "%GEMINI_API_KEY%"=="" set "API_KEY_FOUND=1"
if not "%GOOGLE_API_KEY%"=="" set "API_KEY_FOUND=1"

if "%API_KEY_FOUND%"=="1" goto :key_exists

echo [WARNING] Neither GEMINI_API_KEY nor GOOGLE_API_KEY environment variable is set.
echo           The Gemini-powered analyst chat (/api/chat) will be disabled.
echo(
set /p "USER_KEY=Optional: Enter your Gemini API Key now (or press ENTER to skip): "
if "%USER_KEY%"=="" goto :skip_key
set "GEMINI_API_KEY=%USER_KEY%"
echo API Key set for this session!
goto :skip_key

:key_exists
echo [INFO] Gemini API Key found in environment variables.

:skip_key
echo(

REM 2. Check for uv (backend requirement)
where uv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] 'uv' was not found on your PATH.
    echo         Please make sure uv is installed ^(https://github.com/astral-sh/uv^).
    echo         Press any key to try launching anyway...
    pause >nul
)

REM 3. Free port 8020 if already in use (stale process from a previous run)
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8020 " 2^>nul') do (
    if not "%%p"=="" taskkill /PID %%p /F >nul 2>&1
)

REM 4. Start Backend Server
echo Starting Backend API (uv run quickdata-api)...
start "Quick Data - Backend API" /D "%~dp0backend" cmd /k "uv run quickdata-api"

REM 5. Detect Node Package Manager and Start Frontend Server
echo Starting Frontend UI (Next.js)...
where pnpm >nul 2>&1
if %ERRORLEVEL% equ 0 (
    start "Quick Data - Frontend UI" /D "%~dp0frontend" cmd /k "pnpm dev"
) else (
    start "Quick Data - Frontend UI" /D "%~dp0frontend" cmd /k "npm run dev"
)

echo(
echo =====================================================================
echo [SUCCESS] Both servers are launching in separate windows!
echo(
echo   - Backend API: http://127.0.0.1:8020 (Docs: http://127.0.0.1:8020/docs)
echo   - Frontend UI: http://localhost:3000
echo(
echo   To stop the servers, simply close their respective console windows.
echo =====================================================================
echo(
pause
