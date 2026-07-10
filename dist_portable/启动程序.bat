@echo off
chcp 65001 >nul

echo ╔══════════════════════════════════════════════════════╗
echo ║          Paperfect - Starting...                     ║
echo ╚══════════════════════════════════════════════════════╝

:: Check venv exists
if not exist venv\Scripts\python.exe (
    echo [ERROR] Virtual environment not found!
    echo Please run install.bat first.
    pause
    exit /b 1
)

echo.
echo [1/3] Starting Python Backend Server...
start "Paperfect Backend" cmd /k "cd /d %~dp0 && chcp 65001 >nul && venv\Scripts\python backend\main.py"

echo [2/3] Starting PPT Editor Frontend...
start "PPT Editor" cmd /k "cd /d %~dp0backend\standalone_pdf2ppt\ppt_maker && chcp 65001 >nul && npm run dev"

echo [3/3] Opening browser in 3 seconds...
timeout /t 3 /nobreak >nul
start http://localhost:8000

echo.
echo Application started! You can close this window.
echo Browser should open automatically at http://localhost:8000
echo.
echo To stop: close the two terminal windows that opened.
pause
