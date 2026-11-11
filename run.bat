@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "CHECK_ONLY=0"
set "NO_BUILD=0"
set "NO_PAUSE=0"

:arguments
if "%~1"=="" goto prepare
if /i "%~1"=="--check" goto check_argument
if /i "%~1"=="--no-build" goto no_build_argument
if /i "%~1"=="--no-pause" goto no_pause_argument
echo Usage: run.bat [--check] [--no-build] [--no-pause]
exit /b 2
:check_argument
set "CHECK_ONLY=1"
set "NO_PAUSE=1"
goto next_argument
:no_build_argument
set "NO_BUILD=1"
goto next_argument
:no_pause_argument
set "NO_PAUSE=1"
:next_argument
shift /1
goto arguments

:prepare
pushd "%~dp0"
if errorlevel 1 exit /b 1
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "VITE_API_MODE=bridge"
set "APP_LOG=%~dp0logs\app.log"
if defined FW_UPDATE_LOG_DIR set "APP_LOG=%FW_UPDATE_LOG_DIR%\app.log"
set "PYTHON_ARGS="
if exist ".venv\Scripts\python.exe" goto local_venv
if exist "venv\Scripts\python.exe" goto legacy_venv
where python.exe >nul 2>&1
if not errorlevel 1 goto system_python
where py.exe >nul 2>&1
if not errorlevel 1 goto python_launcher
echo Python was not found. Install Python or create a .venv first.
goto failure
:local_venv
set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
goto dependencies
:legacy_venv
set "PYTHON_EXE=%CD%\venv\Scripts\python.exe"
goto dependencies
:system_python
set "PYTHON_EXE=python.exe"
goto dependencies
:python_launcher
set "PYTHON_EXE=py.exe"
set "PYTHON_ARGS=-3"

:dependencies
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import serial, webview, bottle" >nul 2>&1
if not errorlevel 1 goto build
echo Python dependencies are missing. Run:
echo   "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r backend\requirements.txt
goto failure

:build
if "%NO_BUILD%"=="1" goto verify_build
where npm.cmd >nul 2>&1
if not errorlevel 1 goto frontend_dependencies
echo npm.cmd was not found. Install Node.js first.
goto failure
:frontend_dependencies
if exist "fw_update_UI\node_modules" goto build_ui
echo Frontend dependencies are missing. Run:
echo   npm.cmd --prefix fw_update_UI ci
goto failure
:build_ui
call npm.cmd --prefix fw_update_UI run build
if errorlevel 1 goto failure

:verify_build
if exist "fw_update_UI\dist\index.html" goto launch
echo UI build is missing. Run this launcher without --no-build.
goto failure
:launch
if "%CHECK_ONLY%"=="1" goto success
echo Starting FW Update Tool. Log: "%APP_LOG%"
"%PYTHON_EXE%" %PYTHON_ARGS% backend\main.py
if errorlevel 1 goto failure
:success
echo Completed successfully.
popd
exit /b 0

:failure
set "RUN_EXIT=%ERRORLEVEL%"
if "%RUN_EXIT%"=="0" set "RUN_EXIT=1"
echo Startup failed. Exit code: %RUN_EXIT%
echo Log location: "%APP_LOG%"
if "%NO_PAUSE%"=="0" pause
popd
exit /b %RUN_EXIT%
