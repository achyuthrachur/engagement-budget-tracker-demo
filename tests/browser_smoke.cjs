const { chromium } = require('playwright');
const baseUrl = process.env.BUDGET_TRACKER_TEST_URL || 'http://127.0.0.1:8877';

(async () => {
  let browser;
  try {
  const launchOptions = { headless: true };
  if (process.env.PLAYWRIGHT_EXECUTABLE_PATH) launchOptions.executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH;
  browser = await chromium.launch(launchOptions);
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(10000);
  const errors = [];
  page.on('console', (message) => { if (message.type() === 'error') errors.push(`${message.text()} ${message.location().url||''}`); });
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('response', (response) => { if (response.status() >= 500) errors.push(`${response.status()} ${response.url()}`); });

  await page.goto(`${baseUrl}/proposals/new`);
  await page.getByLabel('Proposal code').fill(`PROP-SMOKE-${Date.now()}`);
  await page.getByLabel('Client name').fill('Proposal Forecast Client');
  await page.getByPlaceholder('Last, First').fill('Planner, Avery');
  await page.getByLabel('Role for proposal person 1').selectOption('Partner');
  if (!(await page.locator('[data-proposal-base-rate="0"]').innerText()).includes('900')) {
    throw new Error('Proposal role selection did not update the base role rate');
  }
  await page.getByLabel('Default discount percent').fill('10');
  await page.getByRole('button', { name: 'Apply discount to all people' }).click();
  if (!(await page.locator('[data-proposal-planning-rate="0"]').innerText()).includes('810')) {
    throw new Error('Proposal discount did not update the planning rate');
  }
  await page.locator('[data-proposal-week$=":budgeted_hours"]').first().fill('16');
  await page.locator('[data-proposal-week$=":forecasted_hours"]').first().fill('0');
  await page.getByRole('button', { name: 'Create proposal' }).click();
  await page.waitForTimeout(750);
  if (!/\/proposals\/\d+$/.test(page.url())) {
    throw new Error(`Proposal creation did not navigate: ${await page.locator('body').innerText()}`);
  }
  await page.getByRole('heading', { name: 'Weekly plan before engagement setup' }).waitFor();
  if (await page.locator('[data-proposal-week$=":forecasted_hours"]').first().inputValue() !== '0') {
    throw new Error('Explicit-zero proposal forecast was not preserved');
  }
  await page.getByLabel('Engagement code').fill(`CONVERTED-${Date.now()}`);
  await page.getByLabel('Engagement lead').fill('Lead, Avery');
  await page.getByLabel(/Conversion phase for/).fill('Discovery');
  await page.getByRole('button', { name: 'Convert proposal' }).click();
  await page.waitForURL(/\/engagements\/\d+$/);
  await page.getByRole('heading', { name: 'Phase breakdown' }).waitFor();

  await page.goto(`${baseUrl}/engagements/new`);
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
  await page.locator('#baseline-confirm').check();
  await page.getByRole('button', { name: 'Create engagement' }).click();
  await page.waitForURL(/\/engagements\/\d+$/);
  await page.getByRole('heading', { name: 'Phase breakdown' }).waitFor();
  await page.locator('[data-expand-phase]').click();
  await page.locator('.inline-phase-detail:not(.loading)').waitFor();
  // "Open forecast editor" is a genuine full navigation, not a pushState hop (the
  // legacy `data-link` intercept was deliberately dropped from this one anchor so
  // it can't diverge from a reload of the same URL - /engagements/<id>/phases/<id>
  // is React-owned (PhaseDetail.jsx) either way now).
  await page.getByRole('link', { name: 'Open forecast editor' }).click();
  await page.getByRole('heading', { name: 'Budget, actual and forecast' }).waitFor();
  await page.getByRole('heading', { name: 'Reforecast a range' }).waitFor();
  await page.getByRole('button', { name: 'Toggle color theme' }).click();
  if ((await page.locator('html').getAttribute('data-theme')) !== 'dark') throw new Error('Dark theme did not activate');
  if (errors.length) throw new Error(`Browser console errors: ${errors.join(' | ')}`);

  await page.setViewportSize({ width: 375, height: 812 });
  await page.reload();
  await page.getByRole('heading', { name: 'Budget, actual and forecast' }).waitFor();
  await page.setViewportSize({ width: 768, height: 900 });
  await page.goto(`${baseUrl}/proposals`);
  await page.getByRole('heading', { name: 'Forecast staffing before creating the engagement' }).waitFor();
  await page.goto(`${baseUrl}/help`);
  await page.getByRole('heading', { name: 'Run the weekly budget' }).waitFor();
  // `/dashboard` is a genuine full navigation (unlike the pushState-driven SPA transitions
  // above), so it hits the Flask route split and serves the new React portfolio page directly
  // (no auto-redirect into an engagement - that behavior was intentionally removed).
  await page.goto(`${baseUrl}/dashboard`);
  await page.getByRole('heading', { name: 'Current engagements' }).waitFor();
  await page.locator('.portfolio-card:not(.proposal-card)').first().click();
  await page.waitForURL(/\/engagements\/\d+$/);
  await page.getByRole('heading', { name: 'Workstream breakdown' }).waitFor();
  if (errors.length) throw new Error(`Browser console errors after dashboard navigation: ${errors.join(' | ')}`);
  await page.locator('.phase-row').first().click();
  await page.locator('.phase-detail.open').waitFor();
  console.log('browser smoke passed');
  } finally {
    await browser?.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
