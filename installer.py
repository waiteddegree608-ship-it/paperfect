import os
import sys
import shutil
import zipfile
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

class PaperfectInstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Paperfect Setup / 安装程序")
        self.root.geometry("620x480")
        self.root.resizable(False, False)
        
        # Determine paths
        if getattr(sys, 'frozen', False):
            self.base_path = sys._MEIPASS
        else:
            self.base_path = os.path.dirname(os.path.abspath(__file__))
            
        self.zip_path = os.path.join(self.base_path, "paperfect_portable.zip")
        
        # Default install directory
        default_dir = os.path.join(os.environ.get("USERPROFILE", "C:\\"), "Paperfect")
        self.install_dir = tk.StringVar(value=default_dir)
        
        self.setup_ui()
        
    def setup_ui(self):
        # Apply style
        style = ttk.Style()
        style.theme_use("vista" if sys.platform == "win32" else "default")
        
        # Header Frame
        header_frame = tk.Frame(self.root, bg="#1E293B", height=80)
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)
        
        header_label = tk.Label(
            header_frame, 
            text="Paperfect - AI Academic Assistant Installer", 
            font=("Segoe UI", 16, "bold"), 
            fg="#FFFFFF", 
            bg="#1E293B",
            anchor="w",
            padx=20
        )
        header_label.pack(fill="both", expand=True)
        
        # Main Content Frame
        self.main_frame = ttk.Frame(self.root, padding=20)
        self.main_frame.pack(fill="both", expand=True)
        
        # Step 1: Welcome & Path Selection
        self.lbl_intro = tk.Label(
            self.main_frame, 
            text="This wizard will install Paperfect on your computer.\nPlease choose the installation folder:",
            font=("Segoe UI", 10),
            justify="left",
            anchor="w"
        )
        self.lbl_intro.pack(fill="x", pady=(0, 10))
        
        path_frame = tk.Frame(self.main_frame)
        path_frame.pack(fill="x", pady=5)
        
        self.txt_path = ttk.Entry(path_frame, textvariable=self.install_dir, font=("Segoe UI", 10))
        self.txt_path.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        btn_browse = ttk.Button(path_frame, text="Browse...", command=self.browse_folder)
        btn_browse.pack(side="right")
        
        # Requirements Label
        self.lbl_req = tk.Label(
            self.main_frame, 
            text="Note: Python 3.10+ is required on the host system.",
            font=("Segoe UI", 9, "italic"),
            fg="#64748B",
            anchor="w"
        )
        self.lbl_req.pack(fill="x", pady=(5, 20))
        
        # Progress & Status (Hidden initially)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.main_frame, variable=self.progress_var, maximum=100)
        
        self.lbl_status = tk.Label(
            self.main_frame, 
            text="Ready to install...", 
            font=("Segoe UI", 9, "bold"),
            fg="#0F172A",
            anchor="w"
        )
        
        # Console output for detailed logs
        self.log_text = tk.Text(
            self.main_frame, 
            height=12, 
            font=("Consolas", 9), 
            bg="#0F172A", 
            fg="#E2E8F0",
            state="disabled"
        )
        
        # Divider line
        separator = ttk.Separator(self.root, orient="horizontal")
        separator.pack(fill="x", side="bottom")
        
        # Bottom Control Frame
        self.control_frame = ttk.Frame(self.root, padding=(15, 10))
        self.control_frame.pack(fill="x", side="bottom")
        
        self.btn_cancel = ttk.Button(self.control_frame, text="Cancel", command=self.root.quit)
        self.btn_cancel.pack(side="right", padx=(15, 0))
        
        self.btn_install = ttk.Button(self.control_frame, text="Install", command=self.start_installation)
        self.btn_install.pack(side="right")
        
    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.install_dir.get(), title="Select Install Folder")
        if folder:
            self.install_dir.set(os.path.normpath(folder))
            
    def append_log(self, text):
        self.log_text.config(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        
    def start_installation(self):
        target = self.install_dir.get().strip()
        if not target:
            messagebox.showerror("Error", "Please select a valid installation directory.")
            return
            
        # Verify ZIP exists
        if not os.path.exists(self.zip_path):
            messagebox.showerror("Error", f"Embedded installer zip package not found at:\n{self.zip_path}")
            return
            
        # Show Progress and Logs
        self.lbl_intro.pack_forget()
        self.txt_path.master.pack_forget()
        self.lbl_req.pack_forget()
        self.btn_install.config(state="disabled")
        
        self.progress_bar.pack(fill="x", pady=(0, 10))
        self.lbl_status.pack(fill="x", pady=(0, 5))
        self.log_text.pack(fill="both", expand=True)
        
        # Start installation in a separate thread
        thread = threading.Thread(target=self.run_install_thread, args=(target,))
        thread.daemon = True
        thread.start()
        
    def run_install_thread(self, target_dir):
        try:
            self.append_log("Starting installation process...")
            self.lbl_status.config(text="Creating directory...")
            self.progress_var.set(5)
            
            # Create target folder
            os.makedirs(target_dir, exist_ok=True)
            self.append_log(f"Target folder created: {target_dir}")
            
            # Kill any existing processes locking the target folder or ports
            self.append_log("Clearing any running Paperfect processes to prevent file locks...")
            try:
                # Format directory path with double backslashes for PowerShell compatibility
                target_dir_escaped = target_dir.replace("\\", "\\\\")
                kill_cmd = (
                    f'Get-Process | Where-Object {{ $_.Path -like "{target_dir_escaped}*" -or '
                    f'$_.CommandLine -like "*{target_dir_escaped}*" }} | Stop-Process -Force -ErrorAction SilentlyContinue'
                )
                subprocess.run(["powershell", "-Command", kill_cmd], creationflags=subprocess.CREATE_NO_WINDOW)
                
                # Also kill port 8900 and 8000 processes
                kill_ports = (
                    'Get-NetTCPConnection -LocalPort 8900, 8000 -ErrorAction SilentlyContinue | '
                    'ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }'
                )
                subprocess.run(["powershell", "-Command", kill_ports], creationflags=subprocess.CREATE_NO_WINDOW)
                self.append_log("  Done clearing locked processes.")
            except Exception as e:
                self.append_log(f"  Warning: Failed to clear locked processes: {e}")

            # Step 1: Extract Zip file
            self.lbl_status.config(text="Extracting application files...")
            self.append_log("Extracting paperfect_portable.zip...")
            
            with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                total_files = len(file_list)
                
                # Check if zip is nested under "dist_portable"
                is_nested = any(f.startswith("dist_portable/") for f in file_list)
                
                for i, file_info in enumerate(file_list):
                    # Compute relative target path
                    rel_name = file_info
                    if is_nested and rel_name.startswith("dist_portable/"):
                        rel_name = rel_name[len("dist_portable/"):]
                        
                    if not rel_name:
                        continue
                        
                    out_path = os.path.join(target_dir, os.path.normpath(rel_name))
                    
                    # Convert to absolute path and handle Windows long path prefix (\\?\)
                    abs_out_path = os.path.abspath(out_path)
                    if sys.platform == "win32" and not abs_out_path.startswith("\\\\?\\"):
                        abs_out_path = "\\\\?\\" + abs_out_path
                        
                    if file_info.endswith('/'):
                        os.makedirs(abs_out_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(abs_out_path), exist_ok=True)
                        with zip_ref.open(file_info) as source, open(abs_out_path, "wb") as target_file:
                            shutil.copyfileobj(source, target_file)
                            
                    # Update progress
                    percent = 5 + int((i / total_files) * 35)  # 5% to 40%
                    self.progress_var.set(percent)
                    if i % 100 == 0 or i == total_files - 1:
                        self.append_log(f"  Extracted ({i}/{total_files}): {rel_name}")
            
            self.append_log("Extraction finished successfully.")
            self.progress_var.set(40)
            
            # Step 2: Run install.bat in target_dir
            self.lbl_status.config(text="Setting up virtual environment & dependencies...")
            self.append_log("Running install.bat. This will take 1-3 minutes...")
            
            install_bat_path = os.path.join(target_dir, "install.bat")
            if not os.path.exists(install_bat_path):
                raise FileNotFoundError("install.bat not found in the extracted files.")
                
            # Run installation process
            # We capture output to show in log
            proc = subprocess.Popen(
                ["cmd.exe", "/c", "install.bat"],
                cwd=target_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Stream logs from installer
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                # Filter out standard progress bar dumps if any
                clean_line = line.strip()
                if clean_line:
                    self.append_log(f"[Setup] {clean_line}")
                    # Estimate setup progress based on logs
                    if "Python virtual environment" in clean_line:
                        self.progress_var.set(50)
                    elif "dependencies from offline cache" in clean_line:
                        self.progress_var.set(65)
                    elif "modified/vendor packages" in clean_line:
                        self.progress_var.set(80)
                    elif "Checking Node.js" in clean_line:
                        self.progress_var.set(90)
            
            proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"install.bat failed with exit code {proc.returncode}")
                
            self.append_log("Install setup process completed successfully.")
            self.progress_var.set(95)
            
            # Step 3: Create Desktop Shortcut
            self.lbl_status.config(text="Creating desktop shortcuts...")
            self.append_log("Creating desktop shortcut...")
            
            desktop_dir = os.path.join(os.environ["USERPROFILE"], "Desktop")
            shortcut_path = os.path.join(desktop_dir, "Paperfect.lnk")
            target_exe = os.path.normpath(os.path.join(target_dir, "paperfect.exe"))
            icon_path = os.path.normpath(os.path.join(target_dir, "frontend", "ppt_editor", "favicon.svg")) # Optional
            
            # Powershell script to create shortcut
            ps_script = f'''
            $WshShell = New-Object -ComObject WScript.Shell
            $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
            $Shortcut.TargetPath = "{target_exe}"
            $Shortcut.WorkingDirectory = "{target_dir}"
            $Shortcut.Description = "Start Paperfect AI Assistant"
            $Shortcut.Save()
            '''
            
            # Execute powershell
            proc_ps = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if proc_ps.returncode == 0:
                self.append_log("Desktop shortcut created successfully.")
            else:
                self.append_log(f"Failed to create desktop shortcut: {proc_ps.stderr}")
                
            self.progress_var.set(100)
            self.lbl_status.config(text="Installation Complete!")
            self.append_log("\n==========================================")
            self.append_log("  SUCCESS! Paperfect has been installed.")
            self.append_log("==========================================")
            
            # Show final success panel
            self.root.after(100, self.show_success_dialog, target_dir)
            
        except Exception as e:
            self.append_log(f"\n[FATAL ERROR] {str(e)}")
            self.lbl_status.config(text="Installation Failed!")
            self.root.after(100, lambda: messagebox.showerror("Installation Error", f"An error occurred during installation:\n{e}"))
            self.btn_cancel.config(text="Close", command=self.root.quit)
            
    def show_success_dialog(self, target_dir):
        # Prompt user to launch
        run_now = messagebox.askyesno(
            "Installation Complete", 
            "Paperfect was installed successfully!\n\nWould you like to start the application now?"
        )
        if run_now:
            launcher_path = os.path.join(target_dir, "启动程序.bat")
            subprocess.Popen(["cmd.exe", "/c", "start", "", launcher_path], cwd=target_dir, shell=True)
            
        self.root.quit()

if __name__ == "__main__":
    # Enable High DPI
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
        
    root = tk.Tk()
    app = PaperfectInstallerApp(root)
    root.mainloop()
