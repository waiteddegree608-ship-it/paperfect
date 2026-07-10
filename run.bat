@echo off

echo ====================================================
echo Starting AI Document to PPT System...
echo ====================================================
echo.

echo Starting Python Backend Server...
start "AI Backend Server" cmd /k "cd /d %~dp0 && chcp 65001 >nul && python backend\main.py"

echo.
echo Launch commands sent. Please wait for the window to start the server.
pause
