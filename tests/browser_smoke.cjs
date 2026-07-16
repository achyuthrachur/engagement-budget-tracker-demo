const { chromium } = require('playwright');

(async () => {
  let browser;
  try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(10000);
  const errors = [];
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', (error) => errors.push(error.message));

  await page.goto('http://127.0.0.1:8877/engagements/new');
  await page.getByLabel('Engagement code').fill(`UI-SMOKE-${Date.now()}`);
  await page.getByLabel('Client name').fill('Browser Smoke Client');
  await page.getByLabel('Complexity mode').selectOption('complex');
  await page.getByLabel('First Monday').fill('2026-07-06');
  await page.getByLabel('Duration in weeks').fill('4');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.locator('[data-team="0:name"]').fill('Tester, Avery');
  await page.locator('[data-team="0:budgeted_hours"]').fill('40');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.locator('[data-phase="0:phase_name"]').fill('Assessment');
  await page.locator('[data-phase="0:phase_code"]').fill('ASSESS');
  await page.locator('[data-phase="0:sow_fees"]').fill('12000');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'Distribute' }).click();
  await page.getByRole('button', { name: 'Create engagement' }).click();
  await page.waitForURL(/\/engagements\/\d+$/);
  await page.getByRole('heading', { name: 'Phase breakdown' }).waitFor();
  await page.getByRole('link', { name: 'Assessment' }).click();
  await page.getByRole('heading', { name: 'Weekly budget, actual and forecast' }).waitFor();
  await page.locator('#theme-toggle').click();
  if ((await page.locator('html').getAttribute('data-theme')) !== 'dark') throw new Error('Dark theme did not activate');
  if (errors.length) throw new Error(`Browser console errors: ${errors.join(' | ')}`);

  await page.setViewportSize({ width: 375, height: 812 });
  await page.reload();
  await page.getByRole('heading', { name: 'Weekly budget, actual and forecast' }).waitFor();
  console.log('browser smoke passed');
  } finally {
    await browser?.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
