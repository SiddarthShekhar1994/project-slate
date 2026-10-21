// Builds the two halves that the desktop app ships, into apps/desktop/build:
//
//   build/web      the Next.js interface as a standalone Node server
//   build/backend  the Python backend as a PyInstaller folder (slate-api.exe)
//
// The interface is built from a scratch copy of apps/web installed with a
// flat (hoisted) node_modules, so the standalone output contains plain files
// and no symlinks: the Windows installer can't carry symlinks, and pnpm's
// usual layout is made of them. Your own apps/web/node_modules is untouched.
//
// Run from anywhere: `pnpm --dir apps/desktop build` (or `dist:win`).

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DESKTOP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(DESKTOP, "..", "..");
const WEB = path.join(REPO, "apps", "web");
const OUT = path.join(DESKTOP, "build");
const WIN = process.platform === "win32";

function run(command, args, options = {}) {
  console.log(`\n> ${command} ${args.join(" ")}`);
  // pnpm is a .cmd shim on Windows, which needs a shell to start.
  execFileSync(command, args, { stdio: "inherit", shell: WIN && command === "pnpm", ...options });
}

function copyTree(from, to, skip = () => false) {
  fs.cpSync(from, to, { recursive: true, filter: (src) => !skip(path.relative(from, src)) });
}

function buildWeb() {
  const scratch = path.join(OUT, "web-src");
  const target = path.join(OUT, "web");
  fs.rmSync(scratch, { recursive: true, force: true });
  fs.rmSync(target, { recursive: true, force: true });
  const skipped = new Set(["node_modules", ".next", "test-results", "playwright-report"]);
  copyTree(WEB, scratch, (rel) => skipped.has(rel.split(path.sep)[0]));
  run("pnpm", ["install", "--frozen-lockfile", "--config.node-linker=hoisted"], { cwd: scratch });
  run("pnpm", ["build"], { cwd: scratch, env: { ...process.env, NEXT_OUTPUT: "standalone", NEXT_TELEMETRY_DISABLED: "1" } });

  const standalone = path.join(scratch, ".next", "standalone");
  copyTree(standalone, target);
  // The standalone server doesn't include the browser assets; they go beside it.
  copyTree(path.join(scratch, ".next", "static"), path.join(target, ".next", "static"));
  if (fs.existsSync(path.join(scratch, "public"))) copyTree(path.join(scratch, "public"), path.join(target, "public"));
  const links = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isSymbolicLink()) links.push(full);
      else if (entry.isDirectory()) walk(full);
    }
  };
  walk(target);
  if (links.length) throw new Error(`the interface build contains symlinks, which the installer can't carry: ${links[0]}`);
  fs.rmSync(scratch, { recursive: true, force: true });
}

function buildBackend() {
  const dist = path.join(OUT, "backend-dist");
  const work = path.join(OUT, "pyinstaller-work");
  const target = path.join(OUT, "backend");
  fs.rmSync(target, { recursive: true, force: true });
  run("uv", ["sync", "--all-packages", "--group", "desktop", "--frozen"], { cwd: REPO });
  run(
    "uv",
    ["run", "--group", "desktop", "pyinstaller", "--noconfirm", "--clean", "--distpath", dist, "--workpath", work,
      path.join(DESKTOP, "backend", "slate-api.spec")],
    { cwd: REPO },
  );
  fs.renameSync(path.join(dist, "slate-api"), target);
  fs.rmSync(dist, { recursive: true, force: true });
  fs.rmSync(work, { recursive: true, force: true });
}

const only = process.argv[2];
fs.mkdirSync(OUT, { recursive: true });
if (only !== "backend") buildWeb();
if (only !== "web") buildBackend();
console.log(`\nBuilt ${only ?? "web and backend"} into ${OUT}`);
