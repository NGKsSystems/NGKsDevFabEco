@echo off
REM NGKsDevFabEco Release Bundle - Batch wrapper
REM Calls run.ps1 via PowerShell

setlocal enabledelayedexpansion

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0
set SCRIPT_PATH=%SCRIPT_DIR%run.ps1

REM Check if PowerShell is available
where /q pwsh
if errorlevel 1 (
    where /q powershell
    if errorlevel 1 (
        echo ERROR: PowerShell not found
        echo Please install PowerShell 5.0 or later
        pause
        exit /b 1
    )
    set PS_CMD=powershell
) else (
    set PS_CMD=pwsh
)

REM Run the PowerShell script
echo ================================================================================
echo NGKsDevFabEco Release Bundle
echo ================================================================================
echo.

%PS_CMD% -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_PATH%"
set FINAL_EXIT=%ERRORLEVEL%

echo.
if %FINAL_EXIT% equ 0 (
    echo ✓ PASS - You are cleared to ship
) else (
    echo ✗ FAIL - See FAILURE_GUIDE.txt for troubleshooting
)
echo.

exit /b %FINAL_EXIT%
