@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ╔══════════════════════════════════════════════════════╗
echo ║        Paperfect 安装程序 / Installer                ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  需要: Python 3.10+ 和 Node.js 18+                  ║
echo ║  Need: Python 3.10+ and Node.js 18+                 ║
echo ╚══════════════════════════════════════════════════════╝
echo.

:: Check Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found! Please install Python 3.10+ first.
    pause
    exit /b 1
)
echo [OK] Python found:
python --version

:: Check Node
node --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Node.js not found! Please install Node.js 18+ first.
    pause
    exit /b 1
)
echo [OK] Node.js found:
node --version
echo.

:: Step 1: Create virtual environment
echo [1/4] Creating Python virtual environment...
if exist venv (
    echo   Removing old venv...
    rmdir /s /q venv
)
python -m venv venv
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to create venv!
    pause
    exit /b 1
)
echo   Done.

:: Step 2: Install wheel packages (offline, no internet needed)
echo.
echo [2/4] Installing Python dependencies from offline cache...
echo   This may take 1-3 minutes...
venv\Scripts\pip install --no-index --find-links=_wheels setuptools wheel
venv\Scripts\pip install --no-index --find-links=_wheels fastapi uvicorn[standard] PyMuPDF openai python-pptx sqlalchemy python-dotenv Jinja2 aiofiles python-multipart pydantic requests pymupdf4llm pywebview
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   [WARN] Some offline installs failed. Trying online fallback...
    venv\Scripts\pip install -i https://pypi.tuna.tsinghua.edu.cn/simple fastapi "uvicorn[standard]" PyMuPDF openai python-pptx sqlalchemy python-dotenv Jinja2 aiofiles python-multipart pydantic requests pymupdf4llm pywebview
)
echo   Done.

:: Step 3: Copy vendor/modified packages
echo.
echo [3/4] Installing modified/vendor packages...
if exist _vendor (
    xcopy /E /Y /Q _vendor\* venv\Lib\site-packages\ >nul 2>&1
    echo   Copied vendor packages to venv.
)
echo   Done.

:: Step 4: Check node_modules
echo.
echo [4/4] Checking Node.js dependencies...
if exist backend\standalone_pdf2ppt\ppt_maker\node_modules (
    echo   node_modules already present. Skipping npm install.
) else (
    echo   Installing Node.js dependencies...
    cd backend\standalone_pdf2ppt\ppt_maker
    call npm install
    cd ..\..\..
)
echo   Done.

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║  Installation complete!                              ║
echo ║  安装完成!                                           ║
echo ╚══════════════════════════════════════════════════════╝
pause
