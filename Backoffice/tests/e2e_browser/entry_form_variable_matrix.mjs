// Driven by test_entry_form_variable_matrix_browser.py. Expects the source matrix to
// resolve three auto-loaded rows to 10, 20 and 30.
import { chromium } from 'playwright-core';

const [base, cookie, aesId, itemId] = process.argv.slice(2);
const results = [];
let failed = false;

const check = (name, ok, extra = '') => {
  results.push(`${ok ? 'PASS' : 'FAIL'} ${name}${ok ? '' : ` ${extra}`}`);
  if (!ok) failed = true;
};

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH,
  args: ['--no-sandbox'],
});

async function newPage() {
  const ctx = await browser.newContext();
  await ctx.addCookies([{ name: 'session', value: cookie, url: base }]);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => results.push(`  pageerror: ${e.message}`));
  return { ctx, page };
}

const snapshot = (page) => page.evaluate(() => (
  [...document.querySelectorAll('input[data-column-type="variable"]')].map((i) => ({
    key: i.dataset.cellKey,
    value: i.value,
    modified: i.classList.contains('variable-modified'),
    bg: i.closest('td')?.style.backgroundColor || '',
  }))
));

async function load(page, settle = 2500) {
  await page.goto(`${base}/assignment/${aesId}`, { waitUntil: 'load' });
  await page.waitForSelector('input[data-column-type="variable"]', { timeout: 30000 });
  await page.waitForTimeout(settle);
  return snapshot(page);
}

const green = (snap) => snap.filter((c) => c.modified || /212, 237, 218/.test(c.bg));
const filled = (snap) => snap.map((c) => c.value).sort().join(',') === '10,20,30';
const healthy = (snap) => snap.length === 3 && green(snap).length === 0 && filled(snap);
const failBootstrap = (page) => page.route('**/entry-bootstrap', (r) => r.fulfill({ status: 500, body: '{}' }));

// Opening the page without touching anything must not leave a local draft behind.
const draftRecords = (page) => page.evaluate(() => new Promise((resolve) => {
  const req = indexedDB.open('ifrc_forms');
  req.onerror = () => resolve([]);
  req.onsuccess = () => {
    const db = req.result;
    const names = [...db.objectStoreNames];
    if (!names.length) return resolve([]);
    const found = [];
    let pending = names.length;
    names.forEach((name) => {
      const all = db.transaction(name).objectStore(name).getAll();
      all.onsuccess = () => {
        all.result.forEach((rec) => found.push(rec));
        if (!--pending) resolve(found);
      };
    });
  };
}));

{
  const { ctx, page } = await newPage();
  await load(page);
  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
  await page.waitForTimeout(800);
  const records = (await draftRecords(page)).filter((r) => r && r.data && Object.keys(r.data).length > 0);
  check('opening the page without edits stores no draft', records.length === 0, JSON.stringify(records).slice(0, 400));
  await ctx.close();
}

// A real edit is still drafted, and the draft restores it.
{
  const { ctx, page } = await newPage();
  await load(page);
  const input = await page.$('input[data-cell-key$="_Actual"]');
  if (input) {
    await input.fill('7');
    await input.dispatchEvent('change');
    await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
    await page.waitForTimeout(800);
    const records = (await draftRecords(page)).filter((r) => r && r.data && Object.keys(r.data).length > 0);
    check('a real edit is still drafted', records.length === 1, JSON.stringify(records).slice(0, 400));
    await page.goto(`${base}/assignment/${aesId}`, { waitUntil: 'load' });
    await page.waitForSelector('input[data-column-type="variable"]', { timeout: 30000 });
    const restoreButton = page.getByRole('button', { name: 'Restore' });
    await restoreButton.click({ timeout: 15000 }).catch(() => results.push('  (no restore prompt appeared)'));
    await page.waitForTimeout(3500);
    const reloaded = await snapshot(page);
    const restored = await page.$eval('input[data-cell-key$="_Actual"]', (el) => el.value);
    check('and restored on the next load without highlighting', healthy(reloaded) && restored === '7',
      JSON.stringify({ reloaded, restored }));
  } else {
    check('Actual column input present', false);
  }
  await ctx.close();
}

// Leaving the page stores an auto-fill draft; every later load restores it.
{
  const { ctx, page } = await newPage();
  for (let n = 1; n <= 5; n++) {
    const snap = await load(page);
    check(`reload #${n}: three filled cells, none highlighted`, healthy(snap), JSON.stringify(snap));
  }
  await ctx.close();
}

// A slow, older resolve with different values must not overwrite the newer one.
{
  const { ctx, page } = await newPage();
  await failBootstrap(page);
  await load(page);
  let calls = 0;
  await page.route('**/api/v1/variables/resolve*', async (route) => {
    const n = ++calls;
    const resp = await route.fetch();
    const body = await resp.json();
    if (n === 1) {
      for (const k of Object.keys(body.results || {})) body.results[k].plan = 999;
      await new Promise((r) => setTimeout(r, 1500));
    }
    await route.fulfill({ response: resp, body: JSON.stringify(body) });
  });
  await page.evaluate((id) => {
    window.matrixHandler.resolveVariablesForAllRows(id);
    window.matrixHandler.resolveVariablesForAllRows(id);
  }, itemId);
  await page.waitForTimeout(4000);
  const snap = await snapshot(page);
  check(`overlapping resolves (calls=${calls}): newest wins, none highlighted`,
    calls === 2 && healthy(snap), JSON.stringify(snap));
  await ctx.close();
}

// Bootstrap failure falls back to the live endpoints.
{
  const { ctx, page } = await newPage();
  await failBootstrap(page);
  const snap = await load(page, 4000);
  check('bootstrap 500: cells resolve through live endpoints', healthy(snap), JSON.stringify(snap));
  await ctx.close();
}

// Both failing: nothing is highlighted, and a later load recovers.
{
  const { ctx, page } = await newPage();
  await failBootstrap(page);
  await page.route('**/api/v1/variables/resolve*', (r) => r.abort());
  const snap = await load(page, 3000);
  check('bootstrap and resolve failing: nothing highlighted', green(snap).length === 0, JSON.stringify(snap));
  await page.unroute('**/api/v1/variables/resolve*');
  await page.unroute('**/entry-bootstrap');
  const recovered = await load(page);
  check('recovers on the next load', healthy(recovered), JSON.stringify(recovered));
  await ctx.close();
}

// Saving through the form keeps the values and does not highlight them.
{
  const { ctx, page } = await newPage();
  await load(page);
  const saveButton = await page.$('#focalDataEntryForm button[name="action"][value="save"]');
  check('save button present', !!saveButton);
  if (saveButton) {
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('ajax=1'), { timeout: 20000 }).catch(() => null),
      saveButton.click({ force: true }),
    ]);
    await page.waitForTimeout(1500);
    const afterSave = await snapshot(page);
    check('after save: none highlighted', healthy(afterSave), JSON.stringify(afterSave));
    const reloaded = await load(page);
    check('reload after save: none highlighted', healthy(reloaded), JSON.stringify(reloaded));
  }
  await ctx.close();
}

await browser.close();
console.log(results.join('\n'));
process.exit(failed ? 1 : 0);
