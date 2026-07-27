const { app, BrowserWindow, dialog } = require('electron');
const path = require('path');
const { spawn, exec } = require('child_process');
const http = require('http');
const fs = require('fs');
const net = require('net');

let backendProcess = null;
let mainWindow = null;
let loadingWindow = null;

function log(msg) {
    const time = new Date().toISOString();
    const logMsg = `[${time}] [Electron Main] ${msg}\n`;
    console.log(logMsg.trim());
    try {
        const rootDir = !app.isPackaged ? __dirname : path.join(process.resourcesPath, '..');
        const logFile = path.join(rootDir, 'app_debug.log');
        fs.appendFileSync(logFile, logMsg, 'utf8');
    } catch (e) {
        // Ignore logging errors
    }
}

process.on('uncaughtException', (error) => {
    log(`UNCAUGHT EXCEPTION: ${error.stack || error.message}`);
});
process.on('unhandledRejection', (reason) => {
    log(`UNHANDLED REJECTION: ${reason}`);
});

function getPortablePath() {
    return !app.isPackaged
        ? __dirname
        : path.join(process.resourcesPath, 'dist_portable');
}

function getLogRoot() {
    return !app.isPackaged ? __dirname : path.join(process.resourcesPath, '..');
}

/** Kill anything listening on the backend port (Windows + portable leftovers). */
function killPortOccupants(port, callback) {
    log(`Freeing port ${port} if occupied...`);
    if (process.platform !== 'win32') {
        callback();
        return;
    }
    exec(`netstat -ano | findstr :${port}`, { windowsHide: true }, (err, stdout) => {
        if (err || !stdout) {
            log(`Port ${port} appears free.`);
            callback();
            return;
        }
        const pids = new Set();
        stdout.split(/\r?\n/).forEach((line) => {
            // Only LISTENING rows
            if (!/LISTENING/i.test(line)) return;
            const parts = line.trim().split(/\s+/);
            const pid = parts[parts.length - 1];
            if (pid && /^\d+$/.test(pid) && pid !== '0') pids.add(pid);
        });
        if (pids.size === 0) {
            log(`No LISTENING process on ${port}.`);
            callback();
            return;
        }
        const myPid = String(process.pid);
        const killList = [...pids].filter((p) => p !== myPid);
        log(`Killing PIDs on port ${port}: ${killList.join(', ')}`);
        let left = killList.length;
        if (left === 0) {
            callback();
            return;
        }
        killList.forEach((pid) => {
            exec(`taskkill /F /PID ${pid} /T`, { windowsHide: true }, (e2, out, stderr) => {
                log(`taskkill ${pid}: ${e2 ? e2.message : 'ok'} ${stderr || out || ''}`);
                left -= 1;
                if (left <= 0) {
                    // brief settle time so the port is released
                    setTimeout(callback, 600);
                }
            });
        });
    });
}

function startBackend() {
    let executablePath;
    let args;
    let cwd = getPortablePath();

    if (!app.isPackaged) {
        const venvPy = path.join(__dirname, 'venv', 'Scripts', 'python.exe');
        const sysPy = 'python';
        executablePath = fs.existsSync(venvPy) ? venvPy : sysPy;
        args = [path.join(__dirname, 'backend', 'main.py'), '--headless'];
    } else {
        executablePath = path.join(process.resourcesPath, 'dist_portable', 'paperfect.exe');
        args = ['--headless'];
    }

    log(`Starting backend executable: ${executablePath}`);
    log(`Arguments: ${args.join(' ')}`);
    log(`Working directory: ${cwd}`);

    const logRoot = getLogRoot();
    const backendLog = path.join(logRoot, 'backend_stdout.log');

    backendProcess = spawn(executablePath, args, {
        cwd: cwd,
        env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',
            // Keep auto-heal off by default to avoid SQLite/UI freezes
            PAPERFECT_AUTO_HEAL: process.env.PAPERFECT_AUTO_HEAL || '0',
        },
        windowsHide: true,
    });

    const appendBackend = (prefix, data) => {
        const text = data.toString();
        if (!text.trim()) return;
        console.log(`[Backend${prefix}] ${text.trim()}`);
        try {
            fs.appendFileSync(backendLog, `[${new Date().toISOString()}]${prefix} ${text}`, 'utf8');
        } catch (_) {}
    };

    backendProcess.stdout.on('data', (data) => appendBackend('', data));
    backendProcess.stderr.on('data', (data) => appendBackend(' ERR', data));

    backendProcess.on('error', (err) => {
        log(`Failed to start backend: ${err.message}`);
        dialog.showErrorBox(
            'Backend Startup Error',
            `Failed to start Python backend:\n${err.message}\nPath: ${executablePath}`
        );
    });

    backendProcess.on('close', (code) => {
        log(`Backend process closed with code ${code}`);
        // Do not auto-destroy main window on first crash during retries
    });
}

/**
 * Prefer /api/health; fall back to /.
 * Requires JSON ok:true when health is available.
 */
function waitForServer(callback, timeout = 90000) {
    const startTime = Date.now();
    const healthUrl = 'http://127.0.0.1:8900/api/health';
    const rootUrl = 'http://127.0.0.1:8900/';
    log(`Waiting for backend server (health → root)...`);

    const tryOnce = (url, isHealth, next) => {
        const req = http.get(url, (res) => {
            let body = '';
            res.on('data', (c) => (body += c));
            res.on('end', () => {
                if (res.statusCode !== 200) {
                    next(false);
                    return;
                }
                if (isHealth) {
                    try {
                        const j = JSON.parse(body);
                        next(!!j.ok);
                        return;
                    } catch (_) {
                        next(false);
                        return;
                    }
                }
                next(true);
            });
        });
        req.on('error', () => next(false));
        req.setTimeout(2000, () => {
            req.destroy();
            next(false);
        });
    };

    const check = () => {
        tryOnce(healthUrl, true, (ok) => {
            if (ok) {
                log('Backend health OK.');
                callback(true);
                return;
            }
            tryOnce(rootUrl, false, (ok2) => {
                if (ok2) {
                    log('Backend root OK (health not ready yet).');
                    callback(true);
                    return;
                }
                if (Date.now() - startTime > timeout) {
                    log('Timeout waiting for backend server.');
                    callback(false);
                } else {
                    setTimeout(check, 400);
                }
            });
        });
    };

    check();
}

function getAppIconPath() {
    const candidates = [
        path.join(__dirname, 'build', 'icon.ico'),
        path.join(__dirname, 'frontend', 'static', 'favicon.png'),
        path.join(__dirname, 'frontend', 'static', 'paperfect_logo.png'),
        path.join(getPortablePath(), 'frontend', 'static', 'favicon.png'),
        path.join(process.resourcesPath || '', 'dist_portable', 'frontend', 'static', 'favicon.png'),
    ];
    for (const c of candidates) {
        try {
            if (c && fs.existsSync(c)) return c;
        } catch (_) {}
    }
    return undefined;
}

function showLoadingWindow() {
    const icon = getAppIconPath();
    loadingWindow = new BrowserWindow({
        width: 500,
        height: 400,
        frame: false,
        resizable: false,
        transparent: true,
        alwaysOnTop: true,
        ...(icon ? { icon } : {}),
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            partition: 'persist:paperfect',
        },
    });

    loadingWindow.loadFile(path.join(__dirname, 'loading.html'));
    loadingWindow.on('closed', () => {
        loadingWindow = null;
    });
}

function runEnvironmentSetup(callback) {
    const cwd = getPortablePath();
    log(`Running install.bat in ${cwd}...`);

    const installProcess = exec('echo. | install.bat', {
        cwd: cwd,
        env: process.env,
        windowsHide: true,
    });

    installProcess.stdout.on('data', (data) => {
        const text = data.toString().trim();
        if (text) console.log(`[Installer] ${text}`);
    });

    installProcess.stderr.on('data', (data) => {
        const text = data.toString().trim();
        if (text) console.error(`[Installer ERR] ${text}`);
    });

    installProcess.on('close', (code) => {
        log(`install.bat finished with exit code ${code}`);
        callback(code === 0);
    });
}

function createMainWindow() {
    const icon = getAppIconPath();
    mainWindow = new BrowserWindow({
        title: 'Paperfect AI Academic Assistant',
        width: 1366,
        height: 768,
        minWidth: 1024,
        minHeight: 700,
        show: false,
        ...(icon ? { icon } : {}),
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            // Persist localStorage (theme / language) across restarts
            partition: 'persist:paperfect',
        },
    });

    mainWindow.setMenuBarVisibility(false);

    // Only show after backend is ready — avoids blank shell / half-loaded Vue
    waitForServer((ready) => {
        if (!ready) {
            if (loadingWindow) {
                try { loadingWindow.destroy(); } catch (_) {}
                loadingWindow = null;
            }
            dialog.showErrorBox(
                'Connection Timeout',
                'The Paperfect backend service did not start within 90s.\n\n' +
                    '1) Close all Paperfect windows\n' +
                    '2) Check app_debug.log and backend_stdout.log\n' +
                    '3) Ensure port 8900 is free\n' +
                    '4) Try run.bat / restart PC if a zombie python holds the port'
            );
            app.quit();
            return;
        }

        mainWindow.loadURL('http://127.0.0.1:8900/');
        mainWindow.once('ready-to-show', () => {
            if (loadingWindow) {
                try { loadingWindow.destroy(); } catch (_) {}
                loadingWindow = null;
            }
            mainWindow.show();
            mainWindow.maximize();
        });

        // If page fails to load Vue (rare), still show window with error page
        mainWindow.webContents.on('did-fail-load', (_e, code, desc) => {
            log(`Main window failed to load: ${code} ${desc}`);
        });
    }, 90000);

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

log(`Starting main.js... app.isPackaged = ${app.isPackaged}`);
const gotTheLock = app.requestSingleInstanceLock();
log(`gotTheLock = ${gotTheLock}`);
if (!gotTheLock) {
    log('Single instance lock failed, quitting!');
    app.quit();
} else {
    app.on('second-instance', () => {
        if (mainWindow) {
            if (mainWindow.isMinimized()) mainWindow.restore();
            mainWindow.focus();
        }
    });

    app.on('ready', () => {
        showLoadingWindow();
        log('Loading window shown. Freeing port 8900 then starting backend...');

        killPortOccupants(8900, () => {
            const cwd = getPortablePath();
            const venvPath = path.join(cwd, 'venv');

            const afterBackendStart = () => {
                // Keep loading window until waitForServer succeeds inside createMainWindow
                createMainWindow();
            };

            if (!fs.existsSync(venvPath) && !app.isPackaged) {
                log('Python venv not found. Running environment setup...');
                runEnvironmentSetup((success) => {
                    if (success) {
                        startBackend();
                        afterBackendStart();
                    } else {
                        if (loadingWindow) {
                            try { loadingWindow.destroy(); } catch (_) {}
                        }
                        dialog.showErrorBox(
                            'Setup Failure',
                            'Failed to configure the Python runtime environment. Please make sure Python and Node.js are installed.'
                        );
                        app.quit();
                    }
                });
            } else {
                startBackend();
                afterBackendStart();
            }
        });
    });
}

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('quit', () => {
    log('Quitting Electron app, terminating backend...');
    if (backendProcess) {
        try {
            if (process.platform === 'win32') {
                exec(`taskkill /F /PID ${backendProcess.pid} /T`, { windowsHide: true });
            } else {
                backendProcess.kill();
            }
        } catch (e) {
            log(`Error killing backend: ${e.message}`);
        }
    }
});

process.on('exit', () => {
    if (backendProcess) {
        try {
            backendProcess.kill();
        } catch (_) {}
    }
});
