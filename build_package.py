"""
Paperfect 便携安装包构建器 v2 (Electron 版)
============================================
"""

import os
import sys
import shutil
import subprocess
import importlib
import sysconfig
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist_portable")
WHEELS_DIR = os.path.join(DIST_DIR, "_wheels")
VENDOR_DIR = os.path.join(DIST_DIR, "_vendor")
SITE_PACKAGES = sysconfig.get_path("purelib")

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
    "pywebview",
]

VENDOR_PACKAGES = [
    "pdf2zh",
    "babeldoc",
]

def banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")

def clean():
    banner("Step 0: Cleaning old build")
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR, ignore_errors=True)
    os.makedirs(DIST_DIR, exist_ok=True)
    
    dist_electron_dir = os.path.join(BASE_DIR, "dist_electron")
    if os.path.exists(dist_electron_dir):
        shutil.rmtree(dist_electron_dir, ignore_errors=True)

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
    
    clean_env_content = (
        "PARSE_API_URL='https://api.siliconflow.cn/v1'\n"
        "PARSE_API_KEY=''\n"
        "PARSE_MODEL='Qwen/Qwen2.5-72B-Instruct'\n"
        "CHAT_API_URL='https://api.siliconflow.cn/v1'\n"
        "CHAT_API_KEY=''\n"
        "CHAT_MODEL='Qwen/Qwen2.5-72B-Instruct'\n"
        "PAPER_API_URL='https://api.siliconflow.cn/v1'\n"
        "PAPER_API_KEY=''\n"
        "PAPER_MODEL='Qwen/Qwen2.5-72B-Instruct'\n"
        "ANNOTATOR_API_URL='https://api.siliconflow.cn/v1'\n"
        "ANNOTATOR_API_KEY=''\n"
        "ANNOTATOR_MODEL='Qwen/Qwen2.5-72B-Instruct'\n"
        "TRANSLATE_API_URL='https://api.siliconflow.cn/v1'\n"
        "TRANSLATE_API_KEY=''\n"
        "TRANSLATE_MODEL='Qwen/Qwen2.5-72B-Instruct'\n"
    )
    with open(os.path.join(DIST_DIR, ".env"), "w", encoding="utf-8") as env_f:
        env_f.write(clean_env_content)
    
    data_dist = os.path.join(DIST_DIR, "data")
    os.makedirs(data_dist, exist_ok=True)
    for f in ["keyword_dict.json", "venue_dict.json"]:
        src = os.path.join(BASE_DIR, "data", f)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(data_dist, f))
            print(f"  Copied data/{f}")
    
    for d in ["papers", "textbooks", "library_raw"]:
        os.makedirs(os.path.join(data_dist, d), exist_ok=True)
    
    ccf_pdf = "第七版中国计算机学会推荐国际学术会议和期刊目录（正式版）.pdf"
    if os.path.exists(os.path.join(BASE_DIR, ccf_pdf)):
        shutil.copy(os.path.join(BASE_DIR, ccf_pdf), os.path.join(DIST_DIR, ccf_pdf))
    
    shutil.copy(os.path.join(BASE_DIR, "requirements.txt"), os.path.join(DIST_DIR, "requirements.txt"))
    print("  Source files copied.")

def download_wheels():
    banner("Step 2: Downloading wheel packages (offline cache)")
    os.makedirs(WHEELS_DIR, exist_ok=True)
    
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"  Python version: {py_ver}")
    print(f"  Platform: {sys.platform}")
    
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
            print(f"  OK")
    
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
- API 密钥需要在解压/安装后的 .env 文件中进行配置，预设密钥已清空以防泄露。
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

def compile_paperfect_app_exe():
    banner("Step 7.5: Compiling Main Application into paperfect.exe")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name", "paperfect",
        "--collect-all", "webview",
        "--collect-all", "fastapi",
        "--collect-all", "uvicorn",
        "--collect-all", "jinja2",
        "--collect-all", "fitz",
        "backend/main.py"
    ]
    print("  Running PyInstaller for main application... this will take 1-2 minutes...")
    result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        print("  [ERROR] PyInstaller compilation for paperfect.exe failed!")
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError("PyInstaller failed")
        
    compiled_app = os.path.join(BASE_DIR, "dist", "paperfect.exe")
    dest_app = os.path.join(DIST_DIR, "paperfect.exe")
    if os.path.exists(compiled_app):
        if os.path.exists(dest_app):
            os.remove(dest_app)
        shutil.move(compiled_app, dest_app)
        print(f"  [OK] Main application compiled successfully: {dest_app}")
    else:
        raise FileNotFoundError(f"Compiled paperfect executable not found at: {compiled_app}")
        
    print("  Cleaning build artifacts for main app...")
    for path in [os.path.join(BASE_DIR, "build"), os.path.join(BASE_DIR, "dist"), os.path.join(BASE_DIR, "paperfect.spec")]:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

def compile_electron_exe():
    banner("Step 8: Packaging Electron Application using electron-builder")
    
    cmd = ["npm.cmd", "run", "dist"]
    print("  Running electron-builder... this will take 1-2 minutes...")
    result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        print("  [ERROR] Electron packaging failed!")
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError("electron-builder failed")
        
    print("  [OK] Electron packaging completed successfully.")
    
    dist_electron_dir = os.path.join(BASE_DIR, "dist_electron")
    installer_path = None
    if os.path.exists(dist_electron_dir):
        for f in os.listdir(dist_electron_dir):
            if f.endswith(".exe") and "Setup" in f:
                installer_path = os.path.join(dist_electron_dir, f)
                break
                
    if not installer_path:
        if os.path.exists(dist_electron_dir):
            for f in os.listdir(dist_electron_dir):
                if f.endswith(".exe"):
                    installer_path = os.path.join(dist_electron_dir, f)
                    break
                
    if installer_path:
        dest_exe = os.path.join(BASE_DIR, "Paperfect_Setup.exe")
        if os.path.exists(dest_exe):
            os.remove(dest_exe)
        shutil.copy(installer_path, dest_exe)
        print(f"  [OK] Copied compiled Electron installer to: {dest_exe}")
        
        release_dir = "E:\\ddl"
        if os.path.exists(release_dir):
            release_exe = os.path.join(release_dir, "Paperfect_Setup.exe")
            try:
                subprocess.run(["powershell", "-Command", "Stop-Process -Name 'Paperfect_Setup' -Force -ErrorAction SilentlyContinue"], creationflags=subprocess.CREATE_NO_WINDOW)
                if os.path.exists(release_exe):
                    os.remove(release_exe)
                shutil.copy(installer_path, release_exe)
                print(f"  [OK] Copied compiled Electron installer to release path: {release_exe}")
            except Exception as e:
                print(f"  [WARNING] Failed to copy to release path: {e}")
    else:
        print("  [WARNING] Could not locate compiled Electron installer EXE inside dist_electron!")

def compile_tkinter_installer():
    banner("Step 9: Packaging portable ZIP and compiling Tkinter Installer")
    
    # 1. Clean up any papers inside dist_portable/data to ensure it's empty!
    data_papers_dir = os.path.join(DIST_DIR, "data", "papers")
    data_textbooks_dir = os.path.join(DIST_DIR, "data", "textbooks")
    data_raw_dir = os.path.join(DIST_DIR, "data", "library_raw")
    db_file = os.path.join(DIST_DIR, "data", "library.db")
    
    for d in [data_papers_dir, data_textbooks_dir, data_raw_dir]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
        
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass
            
    # 2. Create paperfect_portable.zip
    zip_path = os.path.join(BASE_DIR, "paperfect_portable.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)
        
    print("  Creating paperfect_portable.zip from dist_portable... this may take a moment...")
    shutil.make_archive(os.path.join(BASE_DIR, "paperfect_portable"), 'zip', DIST_DIR)
    print("  paperfect_portable.zip created successfully.")
    
    # 3. Compile installer.py to Paperfect_Setup.exe
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name", "Paperfect_Setup",
        "--add-data", "paperfect_portable.zip;.",
        "installer.py"
    ]
    print("  Running PyInstaller for installer.py... this will take 1-2 minutes...")
    result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        print("  [ERROR] PyInstaller compilation for installer.py failed!")
        print(result.stdout)
        print(result.stderr)
        return
        
    # Copy the output executable to BASE_DIR and release_dir
    compiled_exe = os.path.join(BASE_DIR, "dist", "Paperfect_Setup.exe")
    dest_exe = os.path.join(BASE_DIR, "Paperfect_Setup.exe")
    if os.path.exists(compiled_exe):
        if os.path.exists(dest_exe):
            os.remove(dest_exe)
        shutil.move(compiled_exe, dest_exe)
        print(f"  [OK] Standalone Tkinter installer compiled successfully: {dest_exe}")
        
        # Copy to release_dir
        release_dir = "E:\\ddl"
        if os.path.exists(release_dir):
            release_exe = os.path.join(release_dir, "Paperfect_Setup.exe")
            try:
                if os.path.exists(release_exe):
                    os.remove(release_exe)
                shutil.copy(dest_exe, release_exe)
                print(f"  [OK] Copied compiled Tkinter installer to release path: {release_exe}")
            except Exception as e:
                print(f"  [WARNING] Failed to copy to release path: {e}")
                
        # Also zip the final setup for release
        setup_zip = os.path.join(BASE_DIR, "Paperfect_Setup.zip")
        if os.path.exists(setup_zip):
            os.remove(setup_zip)
        with zipfile.ZipFile(setup_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(dest_exe, "Paperfect_Setup.exe")
        print(f"  [OK] Created Setup zip: {setup_zip}")
        
        # Copy setup zip to release dir
        if os.path.exists(release_dir):
            release_zip = os.path.join(release_dir, "Paperfect_Setup.zip")
            try:
                if os.path.exists(release_zip):
                    os.remove(release_zip)
                shutil.copy(setup_zip, release_zip)
                print(f"  [OK] Copied Setup zip to release path: {release_zip}")
            except Exception as e:
                print(f"  [WARNING] Failed to copy zip to release path: {e}")
    else:
        print(f"  [WARNING] Compiled setup executable not found at: {compiled_exe}")
        
    # Clean up zip file and temporary build folders
    if os.path.exists(zip_path):
        os.remove(zip_path)
    for path in [os.path.join(BASE_DIR, "build"), os.path.join(BASE_DIR, "dist"), os.path.join(BASE_DIR, "Paperfect_Setup.spec")]:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)

def main():
    banner("Paperfect Portable Package Builder v2 (Electron)")
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
    compile_paperfect_app_exe()
    compile_electron_exe()
    compile_tkinter_installer()
    
    banner("BUILD COMPLETE!")
    print(f"  Output directory: {DIST_DIR}")
    print(f"  Installer file: Paperfect_Setup.exe")
    print(f"\n  Send Paperfect_Setup.exe to your user/advisor.")
    print(f"  They just need to double-click it to install, choose the folder, and run!")

if __name__ == "__main__":
    main()
