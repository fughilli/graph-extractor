// Headless-Chromium smoke test for the skelgraph viz UI.
// Run after the container is rebuilt with the Playwright overlay:
//   NODE_PATH=$(npm root -g) node /workspace/.pw-smoke.cjs
// Verifies the ES module actually boots (the CDN-import bug left it dead):
// dataset dropdown fills, status clears, a scene renders, no console errors.
const { chromium } = require('playwright');

(async () => {
  const url = process.env.URL || 'http://127.0.0.1:8765/';
  const msgs = [];
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const page = await browser.newPage();
  page.on('console', m => msgs.push(`[${m.type()}] ${m.text()}`));
  page.on('pageerror', e => msgs.push(`[pageerror] ${e.message}`));
  page.on('requestfailed', r => msgs.push(`[reqfail] ${r.url()} :: ${r.failure()?.errorText}`));

  await page.goto(url, { waitUntil: 'load', timeout: 20000 });

  // The bug's tell: dropdown stays empty and #status never leaves "loading…".
  let dropdownOk = false, statusText = '(unset)';
  try {
    await page.waitForFunction(
      () => document.querySelectorAll('#dataset option').length > 0, { timeout: 15000 });
    dropdownOk = true;
  } catch (_) {}
  // Wait for a pipeline run to land (status shows "<n> pts • <mode>").
  try {
    await page.waitForFunction(
      () => /pts/.test(document.getElementById('status')?.textContent || ''), { timeout: 15000 });
  } catch (_) {}
  statusText = await page.$eval('#status', el => el.textContent).catch(() => '(no #status)');

  const optionCount = await page.$$eval('#dataset option', els => els.length).catch(() => -1);
  // WebGL actually initialised?  Count drawn objects in the THREE scene via canvas presence
  const hasCanvas = await page.$eval('#main canvas', c => c.width > 0 && c.height > 0).catch(() => false);
  // Any segments rendered (real pipeline output reached the scene)?
  await page.screenshot({ path: '/workspace/.pw-smoke.png' });

  const errors = msgs.filter(m => m.startsWith('[error]') || m.startsWith('[pageerror]') || m.startsWith('[reqfail]'));

  console.log('URL:            ', url);
  console.log('dataset options:', optionCount, dropdownOk ? 'OK' : 'EMPTY ✗');
  console.log('status text:    ', JSON.stringify(statusText));
  console.log('canvas present: ', hasCanvas);
  console.log('screenshot:      /workspace/.pw-smoke.png');
  console.log('--- console/errors ---');
  console.log(msgs.length ? msgs.join('\n') : '(none)');

  await browser.close();
  const pass = dropdownOk && /pts/.test(statusText) && hasCanvas && errors.length === 0;
  console.log(pass ? '\nRESULT: PASS ✓' : '\nRESULT: FAIL ✗');
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error('harness error:', e); process.exit(2); });
