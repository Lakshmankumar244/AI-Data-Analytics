#!/usr/bin/env node
/**
 * Catalyst predeploy/preserve entry for packaging `_shared` into function trees.
 *
 * The CLI runs this with `shell: true` and empty spawn args. On Windows, a missing
 * `python` (or the Microsoft Store stub) exits 1 and cross-spawn reports ENOENT.
 * Node is already required by the Catalyst CLI, so this launcher finds a real
 * interpreter and then runs sync_into_workers.py.
 */
"use strict";

const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const script = path.join(__dirname, "sync_into_workers.py");

function run(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit" });
  if (result.error && result.error.code === "ENOENT") {
    return false;
  }
  process.exit(result.status == null ? 1 : result.status);
}

function windowsPythonInstalls() {
  const roots = [
    path.join(os.homedir(), "AppData", "Local", "Programs", "Python"),
    path.join(process.env.ProgramFiles || "C:\\Program Files", "Python"),
    path.join(process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)", "Python"),
  ];
  const found = [];
  for (const root of roots) {
    let names;
    try {
      names = fs.readdirSync(root);
    } catch {
      continue;
    }
    for (const name of names) {
      const exe = path.join(root, name, "python.exe");
      if (fs.existsSync(exe)) {
        found.push(exe);
      }
    }
  }
  found.sort().reverse();
  return found;
}

function isWindowsAppsAlias(command) {
  const result = spawnSync("where", [command], { encoding: "utf8" });
  const resolved = (result.stdout || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean);
  return Boolean(resolved && /WindowsApps/i.test(resolved));
}

if (process.platform === "win32") {
  for (const exe of windowsPythonInstalls()) {
    if (run(exe, [script])) {
      process.exit(0);
    }
  }
  if (run("py", ["-3", script])) {
    process.exit(0);
  }
  if (!isWindowsAppsAlias("python") && run("python", [script])) {
    process.exit(0);
  }
} else if (run("python3", [script]) || run("python", [script])) {
  process.exit(0);
}

console.error(
  "Python 3 was not found. Install Python 3 (not the Microsoft Store alias) and retry."
);
process.exit(1);
