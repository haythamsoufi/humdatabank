#!/usr/bin/env node
/**
 * Focal point browser smoke test — mirrors:
 * Backoffice/docs/runbooks/forms-data/focal-point-browser-smoke-test.md
 *
 * Requires Playwright (one-time):
 *   cd Backoffice && npm install -D playwright && npx playwright install chromium
 *
 * Run:
 *   cd Backoffice && node scripts/dev/focal_point_browser_smoke.mjs
 */
import { chromium } from 'playwright';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:5000';
const MATRIX_AES_ID = process.env.MATRIX_AES_ID || '4120';
const SKIP_SUBMIT = process.env.SKIP_SUBMIT !== '0';
const SLOW_MS = 3000;

const report = {
  steps: [],
  consoleErrors: [],
  networkIssues: [],
  ok: true,
};

function step(name, detail, ok = true) {
  report.steps.push({ step: name, ok, detail });
  if (!ok) report.ok = false;
}

async function actAs(page, roleButtonName) {
  await page.goto(`${BASE}/login`);
  await page.getByRole('button', { name: roleButtonName }).click();
  await page.waitForURL((u) => !u.pathname.includes('login'), { timeout: 30000 });
}

async function clickSave(page) {
  const respPromise = page.waitForResponse(
    (r) => r.url().includes(`/forms/assignment/${MATRIX_AES_ID}`) && r.request().method() === 'POST',
    { timeout: 45000 },
  );
  await page.evaluate(() => {
    document.querySelector('button[name="action"][value="save"]')?.click();
  });
  const resp = await respPromise.catch(() => null);
  return resp?.status() ?? null;
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  page.on('console', (msg) => {
    if (msg.type() === 'error' && !/favicon|Forced reflow|deprecated/i.test(msg.text())) {
      report.consoleErrors.push(msg.text());
      report.ok = false;
    }
  });
  page.on('pageerror', (err) => {
    report.consoleErrors.push(err.message);
    report.ok = false;
  });
  page.on('response', (resp) => {
    if (!resp.url().startsWith(BASE)) return;
    const timing = resp.request().timing();
    const ms = timing ? Math.round((timing.responseEnd || 0) - (timing.startTime || 0)) : 0;
    if (resp.status() >= 400 || ms > SLOW_MS) {
      report.networkIssues.push({ url: resp.url(), status: resp.status(), ms });
      if (resp.status() >= 400) report.ok = false;
    }
  });

  try {
    await actAs(page, 'Act as Focal Point');
    step('login_focal', { url: page.url() });

    await page.goto(`${BASE}/forms/assignment/${MATRIX_AES_ID}`);
    await page.waitForTimeout(5000);

    const bootstrapOk = await page.waitForResponse(
      (r) => r.url().includes('entry-bootstrap'),
      { timeout: 15000 },
    ).then((r) => r.status() === 200).catch(() => false);
    step('form_load', { bootstrapOk, matrices: await page.locator('.matrix-container').count() }, bootstrapOk);

    const cell = page.getByRole('textbox', {
      name: /Value for Algerian Red Crescent and # of international delegates integrated with the HNS/,
    });
    if (await cell.count()) {
      await cell.scrollIntoViewIfNeeded();
      await cell.fill('6');
      await cell.blur();
      step('matrix_edit', { value: '6' });
    } else {
      step('matrix_edit', 'matrix cell not found', false);
    }

    const rowSearch = page.getByRole('textbox', { name: 'Search and select a row to add...' }).first();
    if (await rowSearch.count()) {
      await rowSearch.fill('Belg');
      await page.waitForTimeout(2500);
      step('matrix_row_search', { query: 'Belg' });
    }

    const saveStatus = await clickSave(page);
    await page.waitForTimeout(1500);
    step('save', { httpStatus: saveStatus }, saveStatus === 200);

    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(5000);
    const persisted = await cell.inputValue().catch(() => null);
    step('save_persisted', { value: persisted }, persisted === '6');

    if (!SKIP_SUBMIT) {
      page.on('dialog', (d) => d.accept());
      const submitPromise = page.waitForResponse(
        (r) => r.url().includes(`/forms/assignment/${MATRIX_AES_ID}`) && r.request().method() === 'POST',
        { timeout: 45000 },
      );
      await page.evaluate(() => document.querySelector('button[value="submit"]')?.click());
      await page.waitForTimeout(800);
      await page.evaluate(() => document.querySelector('#confirm-ok')?.click());
      const submitStatus = (await submitPromise.catch(() => null))?.status();
      step('submit', { httpStatus: submitStatus, skipped: false });
    } else {
      step('submit', { skipped: true, reason: 'SKIP_SUBMIT=1 (default)' });
    }
  } finally {
    await browser.close();
  }

  console.log(JSON.stringify(report, null, 2));
  process.exit(report.ok ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
