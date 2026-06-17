import os
import sys
import shutil
import urllib.request
import zipfile
import subprocess
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

# Configurations
PYTHON_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
NODE_URL = "https://nodejs.org/dist/v20.11.1/node-v20.11.1-win-x64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist_portable")
RUNTIME_DIR = os.path.join(DIST_DIR, "runtime")
PY_DIR = os.path.join(RUNTIME_DIR, "python")
NODE_DIR = os.path.join(RUNTIME_DIR, "node")

def download_file(url, dest):
    print(f"Downloading {url} to {dest}...")
    urllib.request.urlretrieve(url, dest)
    print("Download completed.")

def unzip_file(zip_path, dest_dir):
    print(f"Extracting {zip_path} to {dest_dir}...")
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(dest_dir)
    print("Extraction completed.")

def main():
    if os.path.exists(DIST_DIR):
        print(f"Cleaning existing {DIST_DIR}...")
        shutil.rmtree(DIST_DIR, ignore_errors=True)
    
    os.makedirs(DIST_DIR, exist_ok=True)
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    
    # 1. Download and set up Python
    py_zip = os.path.join(RUNTIME_DIR, "python.zip")
    download_file(PYTHON_URL, py_zip)
    unzip_file(py_zip, PY_DIR)
    os.remove(py_zip)
    
    # Enable site-packages in embedded Python
    pth_file = os.path.join(PY_DIR, "python311._pth")
    if os.path.exists(pth_file):
        print("Enabling site-packages in python311._pth...")
        with open(pth_file, "r") as f:
            lines = f.readlines()
        new_lines = []
        for line in lines:
            if "import site" in line:
                new_lines.append("import site\n")
            else:
                new_lines.append(line)
        with open(pth_file, "w") as f:
            f.writelines(new_lines)
            
    # Install pip
    pip_py = os.path.join(RUNTIME_DIR, "get-pip.py")
    download_file(GET_PIP_URL, pip_py)
    print("Installing pip...")
    subprocess.run([os.path.join(PY_DIR, "python.exe"), pip_py], check=True)
    os.remove(pip_py)
    
    # 2. Download and set up Node.js
    node_zip = os.path.join(RUNTIME_DIR, "node.zip")
    download_file(NODE_URL, node_zip)
    
    # Node.js zip extracts to a subfolder like node-v20.11.1-win-x64/
    temp_node_extract = os.path.join(RUNTIME_DIR, "node_temp")
    unzip_file(node_zip, temp_node_extract)
    os.remove(node_zip)
    
    # Move files from subfolder to NODE_DIR
    subfolders = [f for f in os.listdir(temp_node_extract) if os.path.isdir(os.path.join(temp_node_extract, f))]
    if subfolders:
        subfolder_path = os.path.join(temp_node_extract, subfolders[0])
        shutil.move(subfolder_path, NODE_DIR)
    shutil.rmtree(temp_node_extract, ignore_errors=True)
    
    # 3. Copy source files
    print("Copying project files...")
    # Copy backend and frontend
    shutil.copytree(os.path.join(BASE_DIR, "backend"), os.path.join(DIST_DIR, "backend"), 
                    ignore=shutil.ignore_patterns("__pycache__", "node_modules", "data", "paperfect_library.db", ".git", ".env"))
    shutil.copytree(os.path.join(BASE_DIR, "frontend"), os.path.join(DIST_DIR, "frontend"))
    
    # Copy configuration files and requirements
    shutil.copy(os.path.join(BASE_DIR, "requirements.txt"), os.path.join(DIST_DIR, "requirements.txt"))
    shutil.copy(os.path.join(BASE_DIR, ".env.example"), os.path.join(DIST_DIR, ".env"))
    
    # Copy PDF directory if exists
    pdf_filename = "第七版中国计算机学会推荐国际学术会议和期刊目录（正式版）.pdf"
    pdf_src = os.path.join(BASE_DIR, pdf_filename)
    if os.path.exists(pdf_src):
        shutil.copy(pdf_src, os.path.join(DIST_DIR, pdf_filename))
        
    # Create empty folders for data
    os.makedirs(os.path.join(DIST_DIR, "data", "textbooks"), exist_ok=True)
    os.makedirs(os.path.join(DIST_DIR, "data", "papers"), exist_ok=True)
    
    # 4. Install Python requirements in the portable environment
    print("Installing build dependencies (setuptools, wheel, hatchling)...")
    subprocess.run([
        os.path.join(PY_DIR, "python.exe"), "-m", "pip", "install", 
        "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
        "setuptools", "wheel", "hatchling"
    ], check=True)
    
    print("Installing Python dependencies...")
    subprocess.run([
        os.path.join(PY_DIR, "python.exe"), "-m", "pip", "install", 
        "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
        "-r", os.path.join(DIST_DIR, "requirements.txt")
    ], check=True)
    
    # 5. Install Node.js requirements
    print("Installing Node dependencies...")
    node_exe = os.path.join(NODE_DIR, "node.exe")
    npm_cli = os.path.join(NODE_DIR, "node_modules", "npm", "bin", "npm-cli.js")
    ppt_maker_dist = os.path.join(DIST_DIR, "backend", "standalone_pdf2ppt", "ppt_maker")
    
    subprocess.run([
        node_exe, npm_cli, "install"
    ], cwd=ppt_maker_dist, check=True)
    
    # 6. Create portable launcher bat
    launcher_content = """@echo off
chcp 65001 >nul
echo ====================================================
echo Starting Portable AI Document to PPT System...
echo ====================================================
echo.

:: Use local runtimes
set PATH=%~dp0runtime\\python;%~dp0runtime\\node;%PATH%

echo [1/2] Starting Python Backend Server...
start "AI Backend Server" cmd /k "cd /d %~dp0 && runtime\\python\\python.exe backend\\main.py"

echo [2/2] Starting Frontend PPT Editor...
start "PPT Editor Frontend" cmd /k "cd /d %~dp0backend\\standalone_pdf2ppt\\ppt_maker && ..\\..\\..\\runtime\\node\\node.exe ..\\..\\..\\runtime\\node\\node_modules\\npm\\bin\\npm-cli.js run dev"

echo.
echo Launch commands sent. Please wait for the two windows to start their servers.
pause
"""
    with open(os.path.join(DIST_DIR, "启动程序.bat"), "w", encoding="utf-8") as f:
        f.write(launcher_content)
        
    print("Zipping package...")
    zip_output = os.path.join(BASE_DIR, "paperfect_portable.zip")
    if os.path.exists(zip_output):
        os.remove(zip_output)
        
    shutil.make_archive(os.path.splitext(zip_output)[0], 'zip', DIST_DIR)
    print(f"Success! Portable package generated at: {zip_output}")

if __name__ == "__main__":
    main()
