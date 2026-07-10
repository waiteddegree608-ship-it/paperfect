"""
Paperfect 便携安装包构建器 v2
==============================
策略：
1. 收集项目源码（backend + frontend）
2. 收集 .env（含真实密钥）
3. 收集 data/ 中的字典文件
4. 用 pipdeptree 分析出项目真正需要的依赖树
5. 用 pip download 下载 wheel 离线包（标准包）
6. 对魔改/git 包，直接从 site-packages 拷贝
7. 收集 node_modules
8. 生成 install.bat 和 启动程序.bat
9. 打包成 zip
"""

import os
import sys
import shutil
import subprocess
import json
import importlib
import sysconfig

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist_portable")
WHEELS_DIR = os.path.join(DIST_DIR, "_wheels")
VENDOR_DIR = os.path.join(DIST_DIR, "_vendor")
SITE_PACKAGES = sysconfig.get_path("purelib")

# ── Project's actual top-level imports (manually curated) ──
# These are the packages our code directly imports.
# pip download will resolve their transitive deps automatically.
CORE_PACKAGES = [
    "fastapi",
    "uvicorn[standard]",
    "PyMuPDF",
    "openai",
    "python-pptx",
    "sqlalchemy",
    "python-dotenv",
    "Jinja2",
    "aiofiles",
    "python-multipart",
    "pydantic",
    "requests",
    "pymupdf4llm",
]

# Packages installed from git or locally modified — cannot pip download.
# We copy these + their unique deps directly from site-packages.
VENDOR_PACKAGES = [
    "pdf2zh",         # PDFMathTranslate (git install, possibly modified)
    "babeldoc",       # dep of pdf2zh (BabelDOC)
]

# Extra site-packages dirs to copy for vendor packages (their unique deps
# that aren't in CORE_PACKAGES). We detect these at build time.

def banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")

def clean():
    banner("Step 0: Cleaning old build")
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR, ignore_errors=True)
    os.makedirs(DIST_DIR, exist_ok=True)

def copy_source():
    banner("Step 1: Copying project source")
    
    ignore = shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".git", ".env", "node_modules",
        "paperfect_library.db", "debug_log.txt", "search_debug.log",
        "dist", ".vite", "debug_output.json"
    )
    
    shutil.copytree(
        os.path.join(BASE_DIR, "backend"),
        os.path.join(DIST_DIR, "backend"),
        ignore=ignore
    )
    shutil.copytree(
        os.path.join(BASE_DIR, "frontend"),
        os.path.join(DIST_DIR, "frontend"),
        ignore=ignore
    )
    
    # Copy .env with real API keys
    shutil.copy(os.path.join(BASE_DIR, ".env"), os.path.join(DIST_DIR, ".env"))
    
    # Copy essential data files (dictionaries for classification)
    data_dist = os.path.join(DIST_DIR, "data")
    os.makedirs(data_dist, exist_ok=True)
    for f in ["keyword_dict.json", "venue_dict.json"]:
        src = os.path.join(BASE_DIR, "data", f)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(data_dist, f))
            print(f"  Copied data/{f}")
    
    # Create empty directories for user data
    for d in ["papers", "textbooks", "library_raw"]:
        os.makedirs(os.path.join(data_dist, d), exist_ok=True)
    
    # Copy the CCF PDF if it exists
    ccf_pdf = "第七版中国计算机学会推荐国际学术会议和期刊目录（正式版）.pdf"
    if os.path.exists(os.path.join(BASE_DIR, ccf_pdf)):
        shutil.copy(os.path.join(BASE_DIR, ccf_pdf), os.path.join(DIST_DIR, ccf_pdf))
    
    # Copy requirements.txt
    shutil.copy(os.path.join(BASE_DIR, "requirements.txt"), os.path.join(DIST_DIR, "requirements.txt"))
    
    print("  Source files copied.")

def download_wheels():
    banner("Step 2: Downloading wheel packages (offline cache)")
    os.makedirs(WHEELS_DIR, exist_ok=True)
    
    # Get current Python version tag for compatible wheels
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"  Python version: {py_ver}")
    print(f"  Platform: {sys.platform}")
    
    # Download each core package + all its transitive deps as wheels
    for pkg in CORE_PACKAGES:
        print(f"\n  Downloading: {pkg}")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "download",
             "--dest", WHEELS_DIR,
             "--no-cache-dir",
             pkg],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  WARNING: Failed to download {pkg}")
            print(f"  stderr: {result.stderr[:300]}")
        else:
            # Count how many files were downloaded
            print(f"  OK")
    
    # Also download setuptools and wheel themselves
    for extra in ["setuptools", "wheel"]:
        subprocess.run(
            [sys.executable, "-m", "pip", "download",
             "--dest", WHEELS_DIR, extra],
            capture_output=True, text=True
        )
    
    wheel_count = len([f for f in os.listdir(WHEELS_DIR) if f.endswith(('.whl', '.tar.gz', '.zip'))])
    print(f"\n  Total wheel files: {wheel_count}")

def copy_vendor_packages():
    banner("Step 3: Copying vendor/modified packages from site-packages")
    os.makedirs(VENDOR_DIR, exist_ok=True)
    
    copied = set()
    for pkg_name in VENDOR_PACKAGES:
        # Find the package directory in site-packages
        try:
            mod = importlib.import_module(pkg_name)
            pkg_path = os.path.dirname(mod.__file__)
            pkg_dir_name = os.path.basename(pkg_path)
        except Exception:
            pkg_dir_name = pkg_name
            pkg_path = os.path.join(SITE_PACKAGES, pkg_dir_name)
        
        if os.path.isdir(pkg_path) and pkg_dir_name not in copied:
            dest = os.path.join(VENDOR_DIR, pkg_dir_name)
            shutil.copytree(pkg_path, dest, ignore=shutil.ignore_patterns("__pycache__"))
            copied.add(pkg_dir_name)
            print(f"  Copied: {pkg_dir_name}/ ({_dir_size_mb(pkg_path):.1f} MB)")
        
        # Also copy .dist-info if exists (for pip to recognize the package)
        for item in os.listdir(SITE_PACKAGES):
            if item.startswith(pkg_name.replace("-","_")) and item.endswith(".dist-info"):
                src = os.path.join(SITE_PACKAGES, item)
                dest = os.path.join(VENDOR_DIR, item)
                if not os.path.exists(dest):
                    shutil.copytree(src, dest)
                    print(f"  Copied: {item}/")

def _dir_size_mb(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            total += os.path.getsize(os.path.join(dirpath, f))
    return total / (1024*1024)

def copy_node_modules():
    banner("Step 4: Copying node_modules for PPT editor")
    ppt_src = os.path.join(BASE_DIR, "backend", "standalone_pdf2ppt", "ppt_maker")
    ppt_dist = os.path.join(DIST_DIR, "backend", "standalone_pdf2ppt", "ppt_maker")
    
    nm_src = os.path.join(ppt_src, "node_modules")
    nm_dist = os.path.join(ppt_dist, "node_modules")
    
    if os.path.isdir(nm_src):
        print(f"  Copying node_modules ({_dir_size_mb(nm_src):.0f} MB)... this may take a while...")
        shutil.copytree(nm_src, nm_dist, ignore=shutil.ignore_patterns(".cache"))
        print("  Done.")
    else:
        print("  WARNING: node_modules not found! Run 'npm install' in ppt_maker first.")

    # Also copy package-lock.json if exists (for npm ci fallback)
    lock = os.path.join(ppt_src, "package-lock.json")
    if os.path.exists(lock):
        shutil.copy(lock, os.path.join(ppt_dist, "package-lock.json"))

def generate_frozen_requirements():
    banner("Step 5: Generating frozen requirements")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        capture_output=True, text=True
    )
    frozen_path = os.path.join(DIST_DIR, "requirements_frozen.txt")
    with open(frozen_path, "w", encoding="utf-8") as f:
        f.write(result.stdout)
    print(f"  Saved to requirements_frozen.txt ({len(result.stdout.splitlines())} packages)")

def create_install_script():
    banner("Step 6: Creating install.bat")
    
    vendor_pkg_names = ", ".join(VENDOR_PACKAGES)
    
    script = r'''@echo off
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
venv\Scripts\pip install --no-index --find-links=_wheels fastapi uvicorn[standard] PyMuPDF openai python-pptx sqlalchemy python-dotenv Jinja2 aiofiles python-multipart pydantic requests pymupdf4llm
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   [WARN] Some offline installs failed. Trying online fallback...
    venv\Scripts\pip install -i https://pypi.tuna.tsinghua.edu.cn/simple fastapi "uvicorn[standard]" PyMuPDF openai python-pptx sqlalchemy python-dotenv Jinja2 aiofiles python-multipart pydantic requests pymupdf4llm
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
echo ║                                                      ║
echo ║  Run "启动程序.bat" to start the application.        ║
echo ║  双击 "启动程序.bat" 启动程序                        ║
echo ╚══════════════════════════════════════════════════════╝
pause
'''
    with open(os.path.join(DIST_DIR, "install.bat"), "w", encoding="utf-8") as f:
        f.write(script)
    print("  install.bat created.")

def create_launcher():
    banner("Step 7: Creating launcher script")
    
    launcher = r'''@echo off
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
'''
    with open(os.path.join(DIST_DIR, "启动程序.bat"), "w", encoding="utf-8") as f:
        f.write(launcher)
    print("  启动程序.bat created.")

def create_readme():
    readme = """# Paperfect - 论文阅读器便携版

## 快速开始

### 第一次使用（安装）
1. 确保电脑已安装 **Python 3.10+** 和 **Node.js 18+**
2. 双击 `install.bat` 运行安装程序
3. 等待安装完成（约 1-3 分钟）

### 启动程序
1. 双击 `启动程序.bat`
2. 浏览器会自动打开 http://localhost:8000
3. 上传 PDF 论文即可开始使用

### 功能
- 论文自动翻译 + AI 批注
- 自动分类（JCR/CCF/核心期刊）
- AI 问答（基于论文内容的 RAG 对话）
- PPT 自动生成
- 实时翻译
- 万能文献搜索

### 注意事项
- API 密钥已内置在 .env 文件中，无需额外配置
- 首次上传论文需要等待 AI 处理（约 1-2 分钟/篇）
- 如需修改 API 配置，编辑 .env 文件即可

### 系统要求
- Windows 10/11
- Python 3.10+
- Node.js 18+
- 约 1GB 磁盘空间
"""
    with open(os.path.join(DIST_DIR, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)
    print("  README.md created.")

def make_zip():
    banner("Step 8: Creating zip archive")
    zip_output = os.path.join(BASE_DIR, "paperfect_portable")
    if os.path.exists(zip_output + ".zip"):
        os.remove(zip_output + ".zip")
    
    print("  Compressing... this may take a few minutes...")
    shutil.make_archive(zip_output, 'zip', BASE_DIR, "dist_portable")
    
    zip_size = os.path.getsize(zip_output + ".zip") / (1024*1024)
    print(f"  Archive created: paperfect_portable.zip ({zip_size:.0f} MB)")

def main():
    banner("Paperfect Portable Package Builder v2")
    print(f"  Source: {BASE_DIR}")
    print(f"  Output: {DIST_DIR}")
    print(f"  Python: {sys.version}")
    print(f"  Site-packages: {SITE_PACKAGES}")
    
    clean()
    copy_source()
    download_wheels()
    copy_vendor_packages()
    copy_node_modules()
    generate_frozen_requirements()
    create_install_script()
    create_launcher()
    create_readme()
    make_zip()
    
    banner("BUILD COMPLETE!")
    print(f"  Output directory: {DIST_DIR}")
    print(f"  Zip file: paperfect_portable.zip")
    print(f"\n  Send paperfect_portable.zip to your advisor.")
    print(f"  She should:")
    print(f"    1. Unzip the file")
    print(f"    2. Double-click install.bat")
    print(f"    3. Double-click 启动程序.bat")

if __name__ == "__main__":
    main()
