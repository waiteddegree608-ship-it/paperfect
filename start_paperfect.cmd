@echo off
cd /d "%~dp0"
npm start
if errorlevel 1 pause
