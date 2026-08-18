const { app, BrowserWindow, dialog, session, nativeImage } = require('electron');
const path = require('path');
const { spawn, exec } = require('child_process');
const http = require('http');
const fs = require('fs');
const net = require('net');

// Windows taskbar / jump-list: must match package.json build.appId
// Call as early as possible so the shell associates the correct icon.
try {
    if (process.platform === 'win32') {
        app.setAppUserModelId('com.paperfect.app');
    }
} catch (_) {}

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

/**
 * Packaged first-run: ensure data dirs + blank .env exist.
 * Installer never ships user secrets; users configure via Settings UI.
 */
function ensurePackagedRuntimeLayout() {
    if (!app.isPackaged) return;
    const root = getPortablePath();
    try {
        const dataDirs = [
            path.join(root, 'data'),
            path.join(root, 'data', 'papers'),
            path.join(root, 'data', 'textbooks'),
            path.join(root, 'data', 'library_raw'),
        ];
        for (const d of dataDirs) {
            if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
        }
        const envPath = path.join(root, '.env');
        if (!fs.existsSync(envPath)) {
            const blank =
                '# Configure via in-app Settings\n' +
                'PARSE_API_URL=\nPARSE_API_KEY=\nPARSE_MODEL=\n' +
                'CHAT_API_URL=\nCHAT_API_KEY=\nCHAT_MODEL=\n' +
                'PAPER_API_URL=\nPAPER_API_KEY=\nPAPER_MODEL=\n' +
                'ANNOTATOR_API_URL=\nANNOTATOR_API_KEY=\nANNOTATOR_MODEL=\n' +
                'TRANSLATE_API_URL=\nTRANSLATE_API_KEY=\nTRANSLATE_MODEL=\n';
            fs.writeFileSync(envPath, blank, 'utf8');
            log('Created blank .env for first run.');
        }
        const backendExe = path.join(root, 'paperfect.exe');
        const nodeExe = path.join(root, 'runtime', 'node', 'node.exe');
        if (!fs.existsSync(backendExe)) {
            log(`WARNING: missing backend: ${backendExe}`);
        }
        if (!fs.existsSync(nodeExe)) {
            log(`WARNING: missing bundled node: ${nodeExe}`);
        }
    } catch (e) {
        log(`ensurePackagedRuntimeLayout: ${e && e.message ? e.message : e}`);
    }
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
        const sysPy = process.platform === 'win32' ? 'python' : 'python3';
        executablePath = fs.existsSync(venvPy) ? venvPy : sysPy;
        args = [path.join(__dirname, 'backend', 'main.py'), '--headless'];
        // Dev backend must run from project root so `import backend...` works
        cwd = __dirname;
    } else {
        executablePath = path.join(process.resourcesPath, 'dist_portable', 'paperfect.exe');
        args = ['--headless'];
        cwd = path.join(process.resourcesPath, 'dist_portable');
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
            PYTHONIOENCODING: 'utf-8',
            PYTHONUTF8: '1',
            // Keep auto-heal off by default to avoid SQLite/UI freezes
            PAPERFECT_AUTO_HEAL: process.env.PAPERFECT_AUTO_HEAL || '0',
        },
        windowsHide: true,
        shell: !app.isPackaged && process.platform === 'win32' && executablePath === 'python',
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
function waitForServer(callback, timeout = 180000) {
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
        // Packaged: icon next to resources / portable frontend
        path.join(process.resourcesPath || '', 'icon.ico'),
        path.join(process.resourcesPath || '', 'dist_portable', 'frontend', 'static', 'app_icon.ico'),
        path.join(getPortablePath(), 'frontend', 'static', 'app_icon.ico'),
        path.join(getPortablePath(), 'frontend', 'static', 'app_icon.png'),
        // Dev / asar-unpacked project tree
        path.join(__dirname, 'build', 'icon.ico'),
        path.join(__dirname, 'build', 'icon.png'),
        path.join(__dirname, 'frontend', 'static', 'app_icon.ico'),
        path.join(__dirname, 'frontend', 'static', 'app_icon.png'),
        path.join(__dirname, 'frontend', 'static', 'paperfect_logo.png'),
        path.join(__dirname, 'frontend', 'static', 'favicon.png'),
    ];
    for (const c of candidates) {
        try {
            if (c && fs.existsSync(c)) return c;
        } catch (_) {}
    }
    return undefined;
}

/** nativeImage for BrowserWindow / taskbar (ICO or PNG). */
function getAppIconImage() {
    const p = getAppIconPath();
    if (!p) return undefined;
    try {
        const img = nativeImage.createFromPath(p);
        if (img && !img.isEmpty()) return img;
    } catch (e) {
        log(`getAppIconImage failed for ${p}: ${e && e.message ? e.message : e}`);
    }
    return undefined;
}

function showLoadingWindow() {
    const icon = getAppIconImage() || getAppIconPath();
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
    const icon = getAppIconImage() || getAppIconPath();
    if (icon) {
        log(`Using app icon: ${typeof icon === 'string' ? icon : getAppIconPath()}`);
    } else {
        log('WARNING: no app icon found — Windows may show default Electron logo');
    }
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

    // Reinforce taskbar icon (some Windows shells ignore constructor icon until shown)
    try {
        if (icon && mainWindow.setIcon) mainWindow.setIcon(icon);
    } catch (_) {}

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
    }, 180000);

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
        // Drop HTTP disk cache for persist:paperfect so redeployed ppt_editor SPA is visible
        try {
            const ses = session.fromPartition('persist:paperfect');
            ses.clearCache().then(() => log('Cleared persist:paperfect HTTP cache.')).catch((e) => {
                log(`clearCache failed: ${e && e.message ? e.message : e}`);
            });
        } catch (e) {
            log(`session clearCache error: ${e && e.message ? e.message : e}`);
        }

        showLoadingWindow();
        log('Loading window shown. Freeing port 8900 then starting backend...');

        killPortOccupants(8900, () => {
            const cwd = getPortablePath();
            // Dev: prefer project venv, otherwise system python (startBackend already falls back).
            // Only run install.bat when packaged portable tree is missing deps — never block
            // dev launch just because venv/ is absent.
            const venvPath = path.join(__dirname, 'venv');
            const hasVenv = fs.existsSync(path.join(venvPath, 'Scripts', 'python.exe'));
            const portableInstall = path.join(cwd, 'install.bat');

            const afterBackendStart = () => {
                // Keep loading window until waitForServer succeeds inside createMainWindow
                createMainWindow();
            };

            if (!app.isPackaged) {
                if (!hasVenv) {
                    log('No project venv — using system python via startBackend().');
                }
                startBackend();
                afterBackendStart();
                return;
            }

            // Packaged release: fully self-contained (paperfect.exe + runtime/node).
            // No install.bat / system Python / system Node required.
            ensurePackagedRuntimeLayout();
            const backendExe = path.join(cwd, 'paperfect.exe');
            if (!fs.existsSync(backendExe)) {
                dialog.showErrorBox(
                    'Installation incomplete',
                    'Bundled backend paperfect.exe is missing.\n\n' +
                        'Please reinstall Paperfect using the official Setup installer.\n' +
                        `Expected: ${backendExe}`
                );
                app.quit();
                return;
            }
            if (fs.existsSync(portableInstall) && !fs.existsSync(path.join(cwd, 'venv'))) {
                // Legacy portable trees only — skip on modern installer builds
                log('Legacy install.bat present; modern builds do not need it. Starting backend directly.');
            }
            startBackend();
            afterBackendStart();
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
