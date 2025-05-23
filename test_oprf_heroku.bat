@echo off
echo ===== Testing OPRF Service on Heroku =====

REM Get the Heroku app name
if "%1"=="" (
    echo No Heroku app name provided
    
    REM Try to get app name from git remote
    for /f "tokens=2 delims=/" %%a in ('git remote -v ^| findstr heroku') do (
        for /f "tokens=1 delims=." %%b in ("%%a") do (
            set HEROKU_APP=%%b
            goto :app_found
        )
    )
    
    echo No Heroku remote found.
    set /p HEROKU_APP="Enter your Heroku app name: "
    
    :app_found
    echo Using Heroku app: %HEROKU_APP%
) else (
    set HEROKU_APP=%1
    echo Using provided Heroku app: %HEROKU_APP%
)

REM Check if the app exists
heroku apps:info --app %HEROKU_APP% > nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: Heroku app %HEROKU_APP% not found.
    exit /b 1
)

echo.
echo Checking if app is running...
heroku ps --app %HEROKU_APP% | findstr "web.*up" > nul
if %ERRORLEVEL% neq 0 (
    echo Warning: Web dyno may not be running.
    echo Starting web dyno...
    heroku ps:scale web=1 --app %HEROKU_APP%
)

heroku ps --app %HEROKU_APP% | findstr "oprf.*up" > nul
if %ERRORLEVEL% neq 0 (
    echo Warning: OPRF dyno may not be running.
    echo Starting OPRF dyno...
    heroku ps:scale oprf=1 --app %HEROKU_APP%
)

echo.
echo Running OPRF integration test...
python test_oprf_service.py https://%HEROKU_APP%.herokuapp.com

if %ERRORLEVEL% equ 0 (
    echo.
    echo ===== OPRF Service Test Completed Successfully =====
) else (
    echo.
    echo ===== OPRF Service Test Failed =====
    echo.
    echo Displaying last 50 log entries to help diagnose issues:
    heroku logs -n 50 --app %HEROKU_APP%
)

echo.
echo Done. 