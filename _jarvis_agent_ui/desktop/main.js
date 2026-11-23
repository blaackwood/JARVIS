// Jarvis Agent - aplicativo desktop (Electron). Sobe o servidor local do Agent UI e mostra
// a interface numa janela propria, sem navegador.
const { app, BrowserWindow, Menu, shell, dialog } = require('electron');
const { spawn, execFile } = require('child_process');
const net = require('net');
const path = require('path');
const fs = require('fs');

const PORT = 8766;
const URL_ = 'http://127.0.0.1:' + PORT + '/';

function findRoot() {
  const cands = [process.env.JARVIS_ROOT, path.resolve(__dirname, '..', '..')];
  for (const c of cands) {
    if (c && fs.existsSync(path.join(c, '_jarvis_agent_ui', 'server.py'))) return c;
  }
  return null;
}
const ROOT = findRoot();
let server = null;
let win = null;

function portUp() {
  return new Promise((res) => {
    const s = net.connect({ port: PORT, host: '127.0.0.1' });
    s.once('connect', () => { s.destroy(); res(true); });
    s.once('error', () => res(false));
    s.setTimeout(600, () => { s.destroy(); res(false); });
  });
}

function ps(cmd) {
  return new Promise((res) => {
    execFile('powershell.exe', ['-NoProfile', '-Command', cmd], { windowsHide: true }, (e, out) => res(String(out || '')));
  });
}

// O exe tem que ser dono do servidor: se ja existe um server.py na porta (de uma execucao
// anterior, iniciado fora do exe), encerra ele para subir um proprio, com o codigo atual.
async function freePort() {
  const out = await ps('Get-NetTCPConnection -State Listen -LocalPort ' + PORT + ' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique');
  const pids = out.split(/\s+/).filter((x) => /^\d+$/.test(x));
  for (const pid of pids) {
    const cmd = await ps('(Get-CimInstance Win32_Process -Filter "ProcessId=' + pid + '").CommandLine');
    if (/server\.py/i.test(cmd)) {
      await new Promise((r) => execFile('taskkill', ['/PID', pid, '/T', '/F'], { windowsHide: true }, () => r()));
    }
  }
  for (let i = 0; i < 24; i++) {
    if (!(await portUp())) return true;
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

async function ensureServer() {
  if (await portUp()) {
    if (!(await freePort())) return false;
  }
  if (!ROOT) return false;
  const venvPy = path.join(ROOT, '.venv', 'Scripts', 'python.exe');
  const py = fs.existsSync(venvPy) ? venvPy : 'python';
  server = spawn(py, [path.join(ROOT, '_jarvis_agent_ui', 'server.py'), '--no-open', '--port', String(PORT)], {
    cwd: ROOT, windowsHide: true, stdio: 'ignore', env: Object.assign({}, process.env, { PYTHONUTF8: '1' }),
  });
  server.on('exit', () => { server = null; });
  for (let i = 0; i < 60; i++) {
    if (await portUp()) return true;
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

function createWindow() {
  const icon = path.join(__dirname, 'icon.ico');
  win = new BrowserWindow({
    width: 1320, height: 840, minWidth: 760, minHeight: 520,
    backgroundColor: '#171817', title: 'JARVIS - Agente', autoHideMenuBar: true,
    icon: fs.existsSync(icon) ? icon : undefined,
    webPreferences: { contextIsolation: true, spellcheck: false },
  });
  win.on('page-title-updated', (e) => e.preventDefault());
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
  win.webContents.on('will-navigate', (e, url) => { if (!url.startsWith(URL_)) { e.preventDefault(); shell.openExternal(url); } });
  win.loadURL(URL_);
  win.on('closed', () => { win = null; });
}

function stopServer() {
  if (server && server.pid) {
    try { execFile('taskkill', ['/PID', String(server.pid), '/T', '/F'], { windowsHide: true }); } catch (e) {}
    server = null;
  }
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus(); } });
  app.whenReady().then(async () => {
    Menu.setApplicationMenu(null);
    const ok = await ensureServer();
    if (!ok) {
      dialog.showErrorBox('Jarvis Agent', 'Nao consegui iniciar o servidor local (porta ' + PORT + ').\nConfira se o Python do Jarvis (.venv) existe em:\n' + (ROOT || '(pasta do Jarvis nao encontrada)'));
      app.quit();
      return;
    }
    createWindow();
  });
  app.on('window-all-closed', () => { stopServer(); app.quit(); });
  app.on('before-quit', stopServer);
}
