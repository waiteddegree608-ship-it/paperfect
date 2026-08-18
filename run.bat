@echo off
setlocal
cd /d "%~dp0"

echo ====================================================
echo  Paperfect start (Electron)
echo ====================================================
echo.

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm not found. Install Node.js first.
  echo Then open a terminal here and run: npm start
  pause
  exit /b 1
)

if not exist "node_modules\electron" (
  echo Installing electron deps...
  call npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed.
    pause
    exit /b 1
  )
)

echo Starting: npm start
echo.
call npm start
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" (
  echo.
  echo [ERROR] start failed code %ERR%
  echo You can also run manually:
  echo   cd /d "%~dp0"
  echo   npm start
  pause
)
endlocal
