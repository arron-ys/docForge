#!/usr/bin/env node
import { execFileSync } from "node:child_process";

const commands = ["node", "npm", "corepack", "pnpm"];
let hasMissing = false;

function which(command) {
  try {
    return execFileSync("which", [command], { encoding: "utf8" }).trim();
  } catch {
    return "";
  }
}

function version(command) {
  try {
    return execFileSync(command, ["-v"], { encoding: "utf8" }).trim().split("\n")[0];
  } catch {
    try {
      return execFileSync(command, ["--version"], { encoding: "utf8" }).trim().split("\n")[0];
    } catch {
      return "";
    }
  }
}

console.log("DocForge frontend environment check\n");

for (const command of commands) {
  const path = which(command);
  if (!path) {
    hasMissing = true;
    console.log(`${command}: missing`);
    continue;
  }

  const commandVersion = version(command) || "version unknown";
  console.log(`${command}: found ${commandVersion} (${path})`);

  if (
    command === "node" &&
    (path.startsWith("/Applications/Codex.app/") ||
      path.startsWith("/private/tmp/") ||
      path.includes("/.codex/tmp/"))
  ) {
    console.log("  warning: this Node path looks temporary or Codex-managed; use a system Node.js install for long-running frontend development.");
  }
}

console.log("");

if (!which("node")) {
  console.log("Node.js is required for the Vue/Vite frontend.");
  console.log("On macOS, install a system Node.js runtime, for example:");
  console.log("  brew install node\n");
}

if (!which("pnpm")) {
  console.log("pnpm is missing.");
  console.log("pnpm is a Node.js package manager, not a Python .venv package.");
  console.log("After installing Node.js, enable pnpm with Corepack:");
  console.log("  corepack enable");
  console.log("  corepack prepare pnpm@latest --activate\n");
}

if (!which("corepack")) {
  console.log("Corepack is missing.");
  console.log("Install a full system Node.js distribution first, then use Corepack to activate pnpm.\n");
}

if (hasMissing) {
  console.log("Frontend toolchain is incomplete. Install the missing tools before running pnpm install / pnpm dev.");
  process.exit(1);
}

console.log("Frontend toolchain looks ready.");
