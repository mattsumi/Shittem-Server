@echo off
echo BAUnpin Injection Utility v2.0
echo Based on BA-Cheeto Architecture
echo ===============================

if "%~1"=="" (
    echo Usage: %0 ^<process_name^> [unload]
    echo.
    echo Examples:
    echo   %0 BlueArchive.exe          - Inject BAUnpin.dll
    echo   %0 BlueArchive.exe unload   - Unload BAUnpin.dll
    echo.
    pause
    exit /b 1
)

set PROCESS_NAME=%1
set DLL_PATH=%~dp0build\bin\Release\BAUnpin.dll
set ACTION=%2

if not exist "%DLL_PATH%" (
    echo ERROR: BAUnpin.dll not found at %DLL_PATH%
    echo Please build the project first.
    pause
    exit /b 1
)

if /i "%ACTION%"=="unload" (
    echo Unloading BAUnpin from %PROCESS_NAME%...
    powershell -ExecutionPolicy Bypass -File "%~dp0inject_v2.ps1" -ProcessName "%PROCESS_NAME%" -DllPath "%DLL_PATH%" -Unload
) else (
    echo Injecting BAUnpin into %PROCESS_NAME%...
    powershell -ExecutionPolicy Bypass -File "%~dp0inject_v2.ps1" -ProcessName "%PROCESS_NAME%" -DllPath "%DLL_PATH%"
)

pause
