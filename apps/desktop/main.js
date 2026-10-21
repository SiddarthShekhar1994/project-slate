// Slate as a desktop app.
//
// On launch this starts the two halves of Slate on free ports on 127.0.0.1:
// the Python backend (FastAPI, SQLite, SymPy grading) and the Next.js server
// for the interface, then shows the interface in a window. Nothing listens
// on the network; data lives under %APPDATA%\Slate\data.
//
// Packaged, both halves ship inside the app (resources/backend is a
// PyInstaller build, resources/web the Next.js standalone server). In
// development (`pnpm start`) the backend runs with uv from the repo and the
// interface with `next dev`, or with a built standalone server when
// SLATE_WEB_DIR points at one.

const { app, BrowserWindow, Menu, dialog, session, shell, utilityProcess } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");

const REPO = path.resolve(__dirname, "..", "..");
const BACKEND_START_MS = 180_000; // first launch: unpack, migrate, import SymPy
const WEB_START_MS = 120_000;

app.setName("Slate");
// Development runs keep their data apart from an installed copy.
app.setPath("userData", path.join(app.getPath("appData"), app.isPackaged ? "Slate" : "Slate (development)"));
if (process.env.SLATE_USER_DATA) app.setPath("userData", process.env.SLATE_USER_DATA);

const state = { backend: null, web: null, window: null, origin: null, quitting: false };

function logDir() {
  const dir = path.join(app.getPath("userData"), "logs");
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function openLog(name) {
  return fs.openSync(path.join(logDir(), name), "w");
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitFor(url, ms, alive, what) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (!alive()) throw new Error(`${what} stopped while starting.`);
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // not listening yet
    }
    await sleep(250);
  }
  throw new Error(`${what} didn't start within ${Math.round(ms / 1000)} seconds.`);
}

function displayName() {
  try {
    const name = os.userInfo().username || "";
    return name ? name.charAt(0).toUpperCase() + name.slice(1) : "";
  } catch {
    return "";
  }
}

function startBackend(port, dataDir) {
  const log = openLog("backend.log");
  const env = { ...process.env, SLATE_USER_NAME: displayName() };
  let command;
  let args;
  let cwd;
  if (app.isPackaged) {
    const exe = process.platform === "win32" ? "slate-api.exe" : "slate-api";
    command = path.join(process.resourcesPath, "backend", exe);
    args = [];
    cwd = path.dirname(command);
  } else {
    command = "uv";
    args = ["run", "--project", REPO, "python", "-m", "slate_api.desktop"];
    cwd = REPO;
  }
  args.push("--port", String(port), "--data-dir", dataDir, "--watch-stdin");
  // stdin stays open as a lifeline: the backend exits when it closes, even if
  // this process is killed.
  const child = spawn(command, args, { cwd, env, stdio: ["pipe", log, log], windowsHide: true });
  child.alive = true;
  child.on("exit", () => {
    child.alive = false;
  });
  child.on("error", (error) => {
    child.alive = false;
    fs.writeSync(log, `could not start the backend: ${error.message}\n`);
  });
  return child;
}

function startWeb(port, apiPort) {
  const log = openLog("web.log");
  const env = {
    ...process.env,
    PORT: String(port),
    HOSTNAME: "127.0.0.1",
    API_ORIGIN: `http://127.0.0.1:${apiPort}`,
    NEXT_TELEMETRY_DISABLED: "1",
  };
  const standalone = app.isPackaged ? path.join(process.resourcesPath, "web") : process.env.SLATE_WEB_DIR;
  if (standalone) {
    const child = utilityProcess.fork(path.join(standalone, "server.js"), [], {
      cwd: standalone,
      env: { ...env, NODE_ENV: "production" },
      stdio: "pipe",
      serviceName: "Slate interface",
    });
    child.alive = true;
    child.stdout?.on("data", (data) => fs.writeSync(log, data));
    child.stderr?.on("data", (data) => fs.writeSync(log, data));
    child.on("exit", () => {
      child.alive = false;
    });
    return child;
  }
  const child = spawn("pnpm", ["--dir", path.join(REPO, "apps", "web"), "dev", "--port", String(port)], {
    env,
    stdio: ["ignore", log, log],
    shell: process.platform === "win32",
    windowsHide: true,
  });
  child.alive = true;
  child.on("exit", () => {
    child.alive = false;
  });
  return child;
}

function isLocal(url) {
  return Boolean(state.origin) && typeof url === "string" && url.startsWith(state.origin);
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    show: false,
    title: "Slate",
    backgroundColor: "#0F1115",
    autoHideMenuBar: true,
    icon: path.join(__dirname, "build-resources", "icon.png"),
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false, spellcheck: false },
  });
  win.once("ready-to-show", () => win.show());
  // Links that open a new window (sources, sign-up pages for API keys) go to
  // the default browser or PDF viewer; the app window only shows Slate.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!isLocal(url) && !url.startsWith("file:")) {
      event.preventDefault();
      if (/^https?:\/\//.test(url)) void shell.openExternal(url);
    }
  });
  win.on("closed", () => {
    state.window = null;
  });
  return win;
}

function allowMicrophone() {
  // Spoken questions record from the microphone; nothing else is granted.
  session.defaultSession.setPermissionRequestHandler((_contents, permission, callback, details) => {
    callback(permission === "media" && isLocal(details.requestingUrl));
  });
  session.defaultSession.setPermissionCheckHandler((_contents, permission, origin) => {
    return permission === "media" && isLocal(origin);
  });
}

async function start() {
  Menu.setApplicationMenu(null);
  allowMicrophone();
  state.window = createWindow();
  await state.window.loadFile(path.join(__dirname, "loading.html"));
  const dataDir = path.join(app.getPath("userData"), "data");
  const apiPort = await freePort();
  let webPort = await freePort();
  while (webPort === apiPort) webPort = await freePort();

  state.backend = startBackend(apiPort, dataDir);
  await waitFor(`http://127.0.0.1:${apiPort}/api/health`, BACKEND_START_MS, () => state.backend.alive, "The Slate backend");
  state.web = startWeb(webPort, apiPort);
  state.origin = `http://127.0.0.1:${webPort}`;
  await waitFor(`${state.origin}/api/health`, WEB_START_MS, () => state.web.alive, "The Slate interface");
  if (state.window) await state.window.loadURL(`${state.origin}/library`);
}

function stopChildren() {
  const { backend, web } = state;
  state.web = null;
  state.backend = null;
  if (web?.alive) web.kill();
  if (backend?.alive) {
    backend.stdin?.end(); // the backend exits by itself when its stdin closes
    setTimeout(() => {
      if (backend.alive) backend.kill();
    }, 3000).unref();
  }
}

async function failed(error) {
  console.error(error);
  if (state.quitting) return;
  const choice = await dialog.showMessageBox({
    type: "error",
    title: "Slate couldn't start",
    message: "Slate couldn't start.",
    detail: `${error.message}\n\nThe log files in ${logDir()} say more.`,
    buttons: ["Open log folder", "Quit"],
    defaultId: 1,
    cancelId: 1,
  });
  if (choice.response === 0) await shell.openPath(logDir());
  app.quit();
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!state.window) return;
    if (state.window.isMinimized()) state.window.restore();
    state.window.focus();
  });
  app.whenReady().then(start).catch(failed);
  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", () => {
    state.quitting = true;
    stopChildren();
  });
}
