const { app, BrowserWindow, ipcMain, shell } = require('electron');
const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const https = require('https');

let mainWindow;
let backendProcess;
let ollamaProcess;

// Detect platform
const isMac = process.platform === 'darwin';
const isWin = process.platform === 'win32';

// ── Media + Web Speech API flags ──
// These MUST be set before the app is ready, so they live at module top level.
app.commandLine.appendSwitch('enable-speech-dispatcher');
app.commandLine.appendSwitch('use-fake-ui-for-media-stream');   // auto-accept getUserMedia
app.commandLine.appendSwitch('allow-http-screen-capture');
app.commandLine.appendSwitch('enable-features', 'WebSpeechAPI,SpeechRecognition');

// Paths
const userDataPath = app.getPath('userData');

// Resolve the Ollama CLI across common install locations.
// (The Ollama.app ships /usr/local/bin/ollama; Homebrew on Apple Silicon
//  uses /opt/homebrew/bin/ollama; Windows installs under LOCALAPPDATA.)
function resolveOllamaPath() {
  if (isWin) {
    const la = process.env.LOCALAPPDATA || '';
    return path.join(la, 'Programs', 'Ollama', 'ollama.exe');
  }
  const candidates = [
    '/usr/local/bin/ollama',
    '/opt/homebrew/bin/ollama',
    path.join(process.env.HOME || '', '.ollama', 'bin', 'ollama'),
    '/Applications/Ollama.app/Contents/Resources/ollama'
  ];
  for (const c of candidates) {
    try { if (fs.existsSync(c)) return c; } catch (_) {}
  }
  return candidates[0]; // sensible default; existence checked elsewhere
}

const ollamaPath = resolveOllamaPath();

const backendPath = app.isPackaged
  ? path.join(process.resourcesPath, 'backend')
  : path.join(__dirname, '..', 'backend');

const backendBin = isMac
  ? path.join(backendPath, 'dist', 'app')
  : path.join(backendPath, 'dist', 'app.exe');

// Check if first launch
function isFirstLaunch() {
  const flagFile = path.join(userDataPath, '.setup-complete');
  return !fs.existsSync(flagFile);
}

function markSetupComplete() {
  fs.writeFileSync(path.join(userDataPath, '.setup-complete'), '1');
}

const APP_URL = 'http://localhost:8000';

// Loading screen shown while the backend boots (so the user sees the Veriify
// spinner instead of a blank page / ERR_CONNECTION_REFUSED).
const LOADING_HTML = `<html>
<head>
<style>
  body {
    margin: 0;
    background: #F0F4FF;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    font-family: system-ui, sans-serif;
  }
  .logo {
    font-size: 42px;
    font-weight: 700;
    background: linear-gradient(135deg, #4F46E5, #7C3AED, #06B6D4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 24px;
  }
  .spinner {
    width: 40px;
    height: 40px;
    border: 3px solid rgba(79,70,229,0.2);
    border-top-color: #4F46E5;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  .msg {
    margin-top: 16px;
    color: #475569;
    font-size: 14px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
  <div class="logo">Veriify</div>
  <div class="spinner"></div>
  <div class="msg">Starting your AI interview coach...</div>
</body>
</html>`;

// Show the loading screen. URL-encoded so the '#' hex colors aren't parsed as a
// URL fragment (which would break the gradient and leave a half-rendered page).
function showLoadingScreen() {
  if (mainWindow) {
    mainWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(LOADING_HTML));
  }
}

// Load the real FastAPI frontend.
function loadApp() {
  if (mainWindow) mainWindow.loadURL(APP_URL);
}

// Create main window
function createWindow(page = 'app') {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 700,
    titleBarStyle: 'hiddenInset',  // Mac: traffic light buttons
    backgroundColor: '#F0F4FF',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,             // Allow mic access
      allowRunningInsecureContent: true
    },
    icon: path.join(__dirname, '..', 'assets', 'icon.png'),
    show: false  // Show after ready
  });

  // Handle permission requests — allow ALL media permissions
  mainWindow.webContents.session.setPermissionRequestHandler((webContents, permission, callback) => {
    const allowedPermissions = ['media', 'microphone', 'audioCapture', 'mediaKeySystem'];
    callback(allowedPermissions.includes(permission));
  });

  // Handle permission check handler
  mainWindow.webContents.session.setPermissionCheckHandler((webContents, permission) => {
    const allowedPermissions = ['media', 'microphone', 'audioCapture'];
    return allowedPermissions.includes(permission);
  });

  if (page === 'setup') {
    mainWindow.loadFile(path.join(__dirname, 'setup.html'));
  } else {
    // Show the loading screen immediately; the real URL is loaded once the
    // backend reports ready (see app.whenReady / finish-setup).
    showLoadingScreen();
  }

  // Core blank-screen fix: if the app URL fails to load because the backend
  // isn't accepting connections yet, retry a handful of times.
  let appLoadRetries = 0;
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDesc, validatedURL) => {
    if (errorCode === -3) return; // ERR_ABORTED (superseded navigation) — ignore
    if (validatedURL && validatedURL.startsWith(APP_URL) && appLoadRetries < 15) {
      appLoadRetries++;
      setTimeout(loadApp, 1000);
    }
  });

  // Grant/trigger media access once the REAL app is loaded (not the loading
  // screen or the setup wizard).
  mainWindow.webContents.on('did-finish-load', () => {
    if (!mainWindow || !mainWindow.webContents.getURL().startsWith(APP_URL)) return;
    appLoadRetries = 0;
    mainWindow.webContents.executeJavaScript(`
      navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
          stream.getTracks().forEach(track => track.stop());
          console.log('Microphone access granted');
        })
        .catch(err => console.log('Mic error:', err));
    `).catch(() => {});
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });
}

// Supabase connection for the bundled app — uses the least-privilege `veriify_app`
// role via the IPv4 connection pooler, so a friend's machine needs no local DB
// and no .env file. (Limited role: SELECT/INSERT/UPDATE/DELETE on the app tables
// only — no admin/DDL rights, so a leaked DMG can't drop tables or escalate.)
const SUPABASE_DATABASE_URL =
  'postgresql://veriify_app.hisgjkkckscrfwgyqpoc:VeriifyApp2026!@aws-1-us-west-2.pooler.supabase.com:5432/postgres';

// Start FastAPI backend — resolves only once Uvicorn is actually up.
function startBackend() {
  return new Promise((resolve, reject) => {
    const cmd = app.isPackaged ? backendBin : 'python3';
    const args = app.isPackaged ? [] : ['app.py'];
    const cwd = app.isPackaged ? backendPath : path.join(__dirname, '..', 'backend');

    const envVars = {
      ...process.env,
      PORT: '8000',
      DATABASE_URL: SUPABASE_DATABASE_URL
    };

    backendProcess = spawn(cmd, args, {
      cwd,
      env: envVars,
      stdio: 'pipe'
    });

    let resolved = false;

    function tryResolve(text) {
      if (!resolved && text.includes('Uvicorn running')) {
        resolved = true;
        // Extra 1s buffer after Uvicorn starts so the socket is accepting.
        setTimeout(resolve, 1000);
      }
    }

    backendProcess.stdout.on('data', (data) => {
      const text = data.toString();
      console.log('[Backend:out]', text);
      tryResolve(text);
    });

    backendProcess.stderr.on('data', (data) => {
      const text = data.toString();
      console.log('[Backend:err]', text);
      tryResolve(text);
    });

    backendProcess.on('error', (err) => {
      console.error('Backend failed to start:', err);
      if (!resolved) {
        resolved = true;
        reject(err);
      }
    });

    // Timeout after 60 seconds — resolve anyway and let the did-fail-load
    // retry bridge a slightly-late server.
    setTimeout(() => {
      if (!resolved) {
        resolved = true;
        resolve();
      }
    }, 60000);
  });
}

// Start Ollama server
function startOllama() {
  return new Promise((resolve) => {
    try {
      ollamaProcess = spawn(ollamaPath, ['serve'], {
        stdio: 'pipe',
        detached: false
      });

      ollamaProcess.stdout.on('data', (data) => {
        if (data.toString().includes('Listening')) resolve();
      });
      ollamaProcess.stderr.on('data', (data) => {
        // `ollama serve` logs to stderr; "Listening on" appears there too.
        if (data.toString().includes('Listening')) resolve();
      });
      ollamaProcess.on('error', () => resolve());
    } catch (_) {
      resolve();
    }

    // Give it 3 seconds regardless (may already be running as a service)
    setTimeout(() => resolve(), 3000);
  });
}

// Check if Ollama is installed
function isOllamaInstalled() {
  try {
    execSync(`"${ollamaPath}" --version`, { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

// Check if model is downloaded
function isModelReady() {
  try {
    const result = execSync(`"${ollamaPath}" list`, { encoding: 'utf8' });
    return result.includes('llama3.1:8b');
  } catch {
    return false;
  }
}

// App startup flow
app.whenReady().then(async () => {
  if (isFirstLaunch() || !isOllamaInstalled() || !isModelReady()) {
    // Show setup screen
    createWindow('setup');
  } else {
    // Normal launch: show the loading spinner instantly, start services, then
    // swap to the real app once the backend is ready.
    createWindow('app');
    try {
      await startOllama();
      await startBackend();
    } catch (err) {
      console.error('Startup error:', err);
    }
    loadApp();
  }
});

// IPC handlers for setup screen
ipcMain.handle('check-ollama', () => isOllamaInstalled());
ipcMain.handle('check-model', () => isModelReady());
ipcMain.handle('get-platform', () => process.platform);

ipcMain.handle('install-ollama', () => {
  if (isMac) {
    shell.openExternal('https://ollama.com/download/mac');
  } else {
    shell.openExternal('https://ollama.com/download/windows');
  }
});

ipcMain.handle('pull-model', (event) => {
  return new Promise((resolve, reject) => {
    const pull = spawn(ollamaPath, ['pull', 'llama3.1:8b']);

    const handle = (data) => {
      // Parse progress and send to renderer
      const text = data.toString();
      const match = text.match(/(\d+)%/);
      if (match) {
        event.sender.send('pull-progress', parseInt(match[1]));
      }
    };
    pull.stdout.on('data', handle);
    pull.stderr.on('data', handle); // ollama reports pull progress on stderr

    pull.on('error', reject);
    pull.on('close', (code) => {
      if (code === 0) resolve(true);
      else reject(new Error('Pull failed'));
    });
  });
});

ipcMain.handle('finish-setup', async () => {
  markSetupComplete();
  showLoadingScreen();            // replace the wizard with the spinner
  try {
    await startOllama();
    await startBackend();
  } catch (err) {
    console.error('Startup error:', err);
  }
  loadApp();
});

// Cleanup on quit
app.on('before-quit', () => {
  if (backendProcess) backendProcess.kill();
  if (ollamaProcess) ollamaProcess.kill();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    if (isFirstLaunch()) {
      createWindow('setup');
    } else {
      // Backend is already running from the initial launch; load the app
      // directly (did-fail-load retry covers the case where it isn't).
      createWindow('app');
      loadApp();
    }
  }
});
