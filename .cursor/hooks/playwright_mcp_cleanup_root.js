#!/usr/bin/env node
/**
 * Safety net: move stray Playwright MCP artifacts from the repo root into
 * .playwright-mcp/screenshots/ (explicit filenames land in cwd — see
 * microsoft/playwright-mcp#1731). Root /*.png and /*.pdf are already gitignored.
 */
const fs = require("fs");
const path = require("path");

const OUTPUT_DIR = ".playwright-mcp/screenshots";
const ROOT_EXTS = new Set([".png", ".jpeg", ".jpg", ".webp", ".pdf"]);

function readStdin() {
  return new Promise((resolve) => {
    const chunks = [];
    process.stdin.on("data", (c) => chunks.push(c));
    process.stdin.on("end", () =>
      resolve(Buffer.concat(chunks).toString("utf8")),
    );
    process.stdin.on("error", () => resolve(""));
  });
}

function uniqueDest(dir, name) {
  const dest = path.join(dir, name);
  if (!fs.existsSync(dest)) return dest;
  const ext = path.extname(name);
  const stem = path.basename(name, ext);
  let i = 1;
  while (true) {
    const candidate = path.join(dir, `${stem}-${i}${ext}`);
    if (!fs.existsSync(candidate)) return candidate;
    i += 1;
  }
}

async function main() {
  await readStdin(); // consume hook payload

  let moved = 0;
  try {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    for (const name of fs.readdirSync(".")) {
      if (!ROOT_EXTS.has(path.extname(name).toLowerCase())) continue;
      let st;
      try {
        st = fs.statSync(name);
      } catch {
        continue;
      }
      if (!st.isFile()) continue;
      const dest = uniqueDest(OUTPUT_DIR, name);
      try {
        fs.renameSync(name, dest);
        moved += 1;
      } catch {
        /* ignore locked/in-use files */
      }
    }
  } catch {
    /* fail open */
  }

  // Silent cleanup only — do not set followup_message (that auto-submits another turn).
  void moved;
  process.stdout.write(JSON.stringify({}));
}

main().catch(() => {
  process.stdout.write(JSON.stringify({}));
});
