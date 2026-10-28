#!/usr/bin/env node
/**
 * Playwright MCP writes explicit `filename` values relative to the workspace
 * root, ignoring --output-dir (microsoft/playwright-mcp#1595 / #1731).
 * Rewrite those paths into .playwright-mcp/screenshots/ before the tool runs.
 */
const fs = require("fs");
const path = require("path");

const OUTPUT_DIR = ".playwright-mcp/screenshots";
const FILE_TOOLS = new Set([
  "browser_take_screenshot",
  "browser_pdf_save",
  "browser_network_requests",
  "browser_console_messages",
  "browser_snapshot",
]);

function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = [];
    process.stdin.on("data", (c) => chunks.push(c));
    process.stdin.on("end", () =>
      resolve(Buffer.concat(chunks).toString("utf8")),
    );
    process.stdin.on("error", reject);
  });
}

function parseToolInput(raw) {
  if (raw == null) return {};
  if (typeof raw === "object") return { ...raw };
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw);
    } catch {
      return {};
    }
  }
  return {};
}

function mcpToolBaseName(toolName) {
  const name = String(toolName || "");
  const m = name.match(/(?:^|:)(browser_[a-z0-9_]+)$/i);
  return m ? m[1].toLowerCase() : "";
}

function rewrittenFilename(filename) {
  if (!filename || typeof filename !== "string") return null;
  const posix = filename.replace(/\\/g, "/").replace(/^\.\/+/, "");
  if (posix === OUTPUT_DIR || posix.startsWith(`${OUTPUT_DIR}/`)) return null;

  const base = path.posix.basename(posix);
  if (!base || base === "." || base === "..") return null;
  return `${OUTPUT_DIR}/${base}`;
}

function rewritePlainMcp(toolInput) {
  const next = rewrittenFilename(toolInput.filename);
  if (!next) return null;
  return { ...toolInput, filename: next };
}

function rewriteCallDynamic(toolInput) {
  const ns = String(toolInput.namespace || "");
  const tool = String(toolInput.toolName || "").toLowerCase();
  if (!/playwright/i.test(ns) || !FILE_TOOLS.has(tool)) return null;

  const args =
    toolInput.arguments && typeof toolInput.arguments === "object"
      ? { ...toolInput.arguments }
      : {};
  const next = rewrittenFilename(args.filename);
  if (!next) return null;
  return {
    ...toolInput,
    arguments: { ...args, filename: next },
  };
}

async function main() {
  let payload = {};
  try {
    const raw = await readStdin();
    if (raw.trim()) payload = JSON.parse(raw);
  } catch {
    process.stdout.write(JSON.stringify({ permission: "allow" }));
    return;
  }

  const toolName = String(payload.tool_name || "");
  const toolInput = parseToolInput(payload.tool_input);
  let updated = null;
  let dest = null;

  if (toolName === "CallDynamicTool") {
    updated = rewriteCallDynamic(toolInput);
    dest = updated?.arguments?.filename;
  } else if (FILE_TOOLS.has(mcpToolBaseName(toolName))) {
    updated = rewritePlainMcp(toolInput);
    dest = updated?.filename;
  }

  if (!updated || !dest) {
    process.stdout.write(JSON.stringify({ permission: "allow" }));
    return;
  }

  try {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  } catch {
    /* best-effort */
  }

  process.stdout.write(
    JSON.stringify({
      permission: "allow",
      updated_input: updated,
      agent_message: `Playwright MCP filename rewritten to ${dest} (explicit filenames ignore --output-dir).`,
    }),
  );
}

main().catch(() => {
  process.stdout.write(JSON.stringify({ permission: "allow" }));
});
