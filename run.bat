@echo off

echo ====================================================
echo Starting AI Document to PPT System...
echo ====================================================
echo.

echo [1/2] Starting Python Backend Server...
start "AI Backend Server" cmd /k "cd /d %~dp0 && chcp 65001 >nul && python web_ui\main.py"

echo [2/2] Starting Frontend PPT Editor...
start "PPT Editor Frontend" cmd /k "cd /d %~dp0standalone_pdf2ppt\ppt_maker && chcp 65001 >nul && npm run dev"

echo.
echo Launch commands sent. Please wait for the two windows to start their servers.
pause
