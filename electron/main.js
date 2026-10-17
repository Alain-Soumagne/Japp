// Processus principal Electron : prépare l'environnement Python (1er lancement), démarre le backend local,
// puis ouvre l'interface. Rien n'est exposé hors de 127.0.0.1.
const { app, BrowserWindow, ipcMain, shell, dialog, session } = require('electron');
const { spawn, execFile } = require('node:child_process');
const http = require('node:http');
const net = require('node:net');
const path = require('node:path');
const fs = require('node:fs');
const { ensureEnv } = require('./bootstrap');

// Tout (journaux, environnement Python, données) vit dans %LOCALAPPDATA%\Japp — jamais dans le dossier d'installation.
const LOCAL = process.env.LOCALAPPDATA || app.getPath('appData');
const USER_DIR = path.join(LOCAL, 'Japp');
// Migration depuis la v0.1.0 (application alors nommée « Cours ») : on déplace le dossier au lieu de le recréer (~3 Go).
try {
  const legacy = path.join(LOCAL, 'Cours');
  if (fs.existsSync(legacy) && !fs.existsSync(USER_DIR)) fs.renameSync(legacy, USER_DIR);
} catch { /* dossier verrouillé : on repartira d'un dossier neuf */ }
app.setPath('userData', USER_DIR);

const PACKAGED = app.isPackaged;
const RES = process.resourcesPath;
const APP_ROOT = path.resolve(__dirname, '..');                       // dev : dossier du dépôt
const USER = app.getPath('userData');
const ALLOWED_EXTERNAL = ['https://ollama.com/', 'https://github.com/'];

let PORT = Number(process.env.JAPP_PORT || 0);
let BASE = '';
let backend = null;
let win = null;
let quitting = false;

const exists = (p) => { try { return fs.existsSync(p); } catch { return false; } };

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', reject);
    srv.listen(0, '127.0.0.1', () => { const { port } = srv.address(); srv.close(() => resolve(port)); });
  });
}

function health(timeout = 1500) {
  return new Promise((resolve) => {
    const req = http.get(`${BASE}/health`, { timeout }, (res) => { res.resume(); resolve(res.statusCode === 200); });
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
  });
}

function status(text, pct = null, hint = '') {
  if (win && !win.isDestroyed()) {
    win.webContents.executeJavaScript(`window.setStatus && window.setStatus(${JSON.stringify(text)}, ${pct}, ${JSON.stringify(hint)})`).catch(() => {});
  }
}

function logStream(name) {
  fs.mkdirSync(USER, { recursive: true });
  const file = path.join(USER, name);
  try { if (fs.statSync(file).size > 5 * 1024 * 1024) fs.writeFileSync(file, ''); } catch { /* absent */ }
  return fs.openSync(file, 'a');
}

async function resolvePython() {
  if (process.env.JAPP_PYTHON) return process.env.JAPP_PYTHON;
  if (!PACKAGED) {
    const dev = path.join(APP_ROOT, '.venv', 'Scripts', 'python.exe');
    if (exists(dev)) return dev;
    throw new Error("Environnement de développement introuvable. Crée-le :\n  uv venv --python 3.12 .venv\n  uv pip install --python .venv\\Scripts\\python.exe -r requirements.txt");
  }
  const setupLog = logStream('setup.log');
  return ensureEnv({
    uvPath: path.join(RES, 'uv', 'uv.exe'),
    requirementsPath: path.join(RES, 'requirements.txt'),
    envDir: path.join(USER, 'env'),
    cacheDir: path.join(USER, 'uv-cache'),
    onStatus: (t, p) => status(t, p, 'Première ouverture uniquement — connexion internet requise.'),
    onLog: (l) => fs.writeSync(setupLog, l + '\n'),
  });
}

async function startBackend() {
  if (!PORT) PORT = await freePort();
  BASE = `http://127.0.0.1:${PORT}`;
  if (process.env.JAPP_PORT && (await health())) return;              // backend de dev déjà lancé

  const py = await resolvePython();
  status('Démarrage du moteur local…', null);
  const log = logStream('backend.log');
  const backendDir = PACKAGED ? path.join(RES, 'backend') : path.join(APP_ROOT, 'backend');
  const env = {
    ...process.env,
    HF_HUB_DISABLE_SYMLINKS_WARNING: '1',
    PYTHONUTF8: '1',
    JAPP_DATA_DIR: process.env.JAPP_DATA_DIR || path.join(USER, 'data'),
  };
  if (PACKAGED) env.JAPP_FRONTEND_DIR = path.join(RES, 'frontend');
  backend = spawn(py, ['-m', 'app', '--port', String(PORT)], { cwd: backendDir, env, stdio: ['ignore', log, log], windowsHide: true });
  backend.on('exit', (code) => {
    backend = null;
    if (!quitting) dialog.showErrorBox('Moteur arrêté', `Le moteur local s'est arrêté (code ${code}).\nJournal : ${path.join(USER, 'backend.log')}`);
  });
  for (let i = 0; i < 180; i++) {                                       // ~90 s (chargement initial des bibliothèques)
    if (await health()) return;
    if (!backend) throw new Error('Le moteur local a quitté au démarrage.');
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error('Le moteur local ne répond pas.');
}

function stopBackend() {
  if (!backend) return;
  const pid = backend.pid;
  backend = null;
  execFile('taskkill', ['/PID', String(pid), '/T', '/F'], () => {});    // python + Ollama lancé par l'app
}

function openExternal(url) {
  if (typeof url !== 'string') return;
  if (BASE && url.startsWith(BASE + '/')) {
    new BrowserWindow({ width: 1280, height: 760, autoHideMenuBar: true, backgroundColor: '#1d1b19',
      webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false } }).loadURL(url);
  } else if (ALLOWED_EXTERNAL.some((p) => url.startsWith(p))) {
    shell.openExternal(url);
  }
}

async function createWindow() {
  // aucune permission web (caméra, micro, géoloc, notifications…) n'est jamais accordée
  session.defaultSession.setPermissionRequestHandler((_wc, _perm, cb) => cb(false));
  session.defaultSession.setPermissionCheckHandler(() => false);

  win = new BrowserWindow({
    width: 1400, height: 900, minWidth: 980, minHeight: 600, backgroundColor: '#1d1b19',
    title: 'Japp – transcription locale', autoHideMenuBar: true,
    icon: path.join(__dirname, 'build', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true,
      allowRunningInsecureContent: false, spellcheck: false,
    },
  });
  win.setMenuBarVisibility(false);
  win.webContents.setWindowOpenHandler(({ url }) => { openExternal(url); return { action: 'deny' }; });
  // aucune navigation hors de l'application (ex. un fichier lâché à côté de la zone de dépôt)
  win.webContents.on('will-navigate', (e, url) => { if (!BASE || !url.startsWith(BASE + '/')) e.preventDefault(); });

  await win.loadFile(path.join(__dirname, 'splash.html'));
  try {
    await startBackend();
    await win.loadURL(BASE + '/');
  } catch (err) {
    dialog.showErrorBox('Démarrage impossible', `${err.message || err}\n\nJournaux : ${USER}`);
    app.quit();
  }
}

ipcMain.on('open-external', (event, url) => {
  if (win && event.sender === win.webContents) openExternal(url);       // uniquement depuis la fenêtre principale
});

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
  app.whenReady().then(createWindow);
  app.on('before-quit', () => { quitting = true; stopBackend(); });
  app.on('window-all-closed', () => app.quit());
}
