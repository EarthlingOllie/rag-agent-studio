const { chromium } = require('playwright');
const OUT = process.argv[2] ?? __dirname, B = 'http://localhost:5173', HOST = 'http://localhost:5175', BLOCKED = 'http://localhost:5176';
const OWNER = { email: 'owner@northwind.example', password: 'northwind-owner-demo' };
(async () => {
  const browser = await chromium.launch();
  const opts = { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, baseURL: B, colorScheme: 'light' };
  const ctx = await browser.newContext(opts);
  const page = await ctx.newPage();
  const shot = async (n, p = page, full = false) => { await p.waitForTimeout(900); await p.screenshot({ path: `${OUT}/${n}.png`, fullPage: full }); console.log('shot', n); };
  const step = async (name, p, fn) => { try { await fn(); } catch (e) { console.log('FAIL', name, e.message.split('\n')[0]); await p.screenshot({ path: `${OUT}/fail-${name}.png`, fullPage: true }).catch(() => {}); } };
  const menu = (p, m) => p.getByRole('banner').getByRole('button', { name: new RegExp(`^(.+, )?${m}$`) });
  const open = async (p, m, item) => { await menu(p, m).click(); await p.getByRole('menu', { name: m }).getByRole('menuitem', { name: item, exact: true }).click(); await p.waitForLoadState('networkidle'); };

  await step('signin', page, async () => { await page.goto('/sign-in'); await shot('41-sign-in-reskin'); });
  await page.request.post('/api/auth/sign-in', { data: OWNER });
  await page.goto('/'); await page.waitForLoadState('networkidle');
  await step('projects', page, async () => {
    await open(page, 'Organisation sections', 'Projects'); await shot('42-projects-reskin');
    await page.getByRole('link', { name: 'Northwind Handbook' }).click();
    await page.getByRole('table', { name: 'Documents' }).getByRole('cell', { name: 'Ready' }).first().waitFor({ timeout: 120000 });
    await shot('43-documents-reskin', page, true);
    await menu(page, 'Project sections').click(); await page.getByRole('menu', { name: 'Project sections' }).waitFor();
    await shot('44-breadcrumb-menu'); await page.keyboard.press('Escape');
  });
  await step('viewer', page, async () => {
    await page.getByRole('link', { name: 'northwind-staff-handbook.md' }).click();
    const flagged = page.getByRole('region', { name: 'Chunks' }).getByRole('listitem').filter({ has: page.getByRole('note', { name: 'Guardrail flag' }) }).first();
    await flagged.waitFor({ timeout: 15000 }); await flagged.scrollIntoViewIfNeeded(); await page.evaluate(() => window.scrollBy(0, -200));
    await shot('45-flagged-chunk');
  });
  await step('agent', page, async () => {
    await open(page, 'Project sections', 'Agents'); await shot('46-agents-list');
    await page.getByRole('link', { name: 'HR helper' }).click();
    await page.getByRole('heading', { level: 2, name: 'HR helper' }).waitFor({ timeout: 15000 });
    const tl = page.getByRole('list', { name: 'Live History' }); await tl.getByRole('listitem').first().waitFor({ timeout: 15000 });
    await tl.scrollIntoViewIfNeeded(); await page.evaluate(() => window.scrollBy(0, -150)); await shot('47-live-history-seeded');
  });
  await step('analytics', page, async () => {
    await open(page, 'Project sections', 'Analytics');
    await page.getByRole('combobox', { name: 'Agent' }).selectOption({ label: 'HR helper' });
    for (const [v, n] of [['v1', '48-analytics-v1'], ['v2', '49-analytics-v2'], ['v3 (Live)', '50-analytics-v3-low-confidence']]) {
      await page.getByRole('combobox', { name: /^Version/ }).selectOption({ label: v });
      await page.getByRole('list', { name: `Key numbers for ${v.replace(/ \(Live\)$/, '')}` }).getByRole('listitem', { name: 'Thumbs-up rate' }).getByText(/95% interval/).waitFor({ timeout: 15000 });
      await shot(n, page, n.startsWith('48'));
    }
  });
  await step('conversations', page, async () => {
    await open(page, 'Project sections', 'Conversations'); await page.getByRole('table', { name: 'Conversations' }).waitFor({ timeout: 15000 }); await shot('51-conversations-seeded');
  });
  await step('cost', page, async () => {
    await open(page, 'Organisation sections', 'Cost');
    await page.getByRole('table', { name: 'Cost by Project' }).getByRole('row').nth(1).waitFor({ timeout: 15000 }); await shot('52-organisation-cost', page, true);
  });
  await step('settings', page, async () => {
    await open(page, 'Organisation sections', 'Settings'); await shot('53-organisation-settings-reskin', page, true);
    await open(page, 'Organisation settings', 'Audit'); await page.getByRole('table', { name: 'Audit Events' }).getByRole('row').nth(1).waitFor({ timeout: 15000 }); await shot('54-audit-seeded');
  });
  await step('shop', page, async () => {
    const p = await ctx.newPage(); await p.goto(`${HOST}/demo/`);
    const w = p.frameLocator('iframe[title="Chat"]');
    await w.getByRole('button', { name: 'Open chat' }).click({ timeout: 15000 });
    await w.getByLabel('Message').fill('Can I return a jar of honey?'); await w.getByRole('button', { name: 'Send' }).click();
    await w.getByRole('log', { name: 'Conversation' }).getByRole('listitem', { name: 'Product FAQ', exact: true }).getByText(/Demo model/).waitFor({ timeout: 30000 });
    await shot('55-demo-shop-widget', p); await p.goto(`${HOST}/demo/inline.html`); await p.waitForTimeout(3000); await shot('56-demo-inline', p); await p.close();
  });
  await step('blocked', page, async () => { const p = await ctx.newPage(); await p.goto(`${BLOCKED}/`); await p.waitForTimeout(4000); await shot('57-disallowed-origin', p); await p.close(); });
  await step('attacks', page, async () => {
    const p = await ctx.newPage(); await p.goto(`${HOST}/demo/attacks.html`);
    for (const b of ['Instruction override', 'Prompt extraction', 'Role-play jailbreak', 'Encoded attack (base64)', 'Benign control']) {
      await p.getByRole('button', { name: b, exact: true }).click({ timeout: 15000 });
      await p.getByRole('status').filter({ hasText: `${b}: done.` }).waitFor({ timeout: 45000 });
    }
    await shot('58-attack-panel', p, true); await p.close();
  });
  await step('budget', page, async () => {
    const p = await ctx.newPage(); await p.goto(`${HOST}/demo/budget.html`);
    const w = p.frameLocator('iframe[title="Chat"]'); await w.getByRole('heading', { name: 'Low-budget helper' }).waitFor({ timeout: 15000 });
    await p.getByRole('button', { name: "Use up today's Token Budget" }).click();
    await p.getByRole('status').filter({ hasText: "Today's Token Budget is spent" }).waitFor({ timeout: 15000 });
    await w.getByLabel('Message').fill('Do you sell honey?'); await w.getByRole('button', { name: 'Send' }).click();
    await w.getByRole('alert').waitFor({ timeout: 15000 }); await shot('59-token-budget-spent', p); await p.close();
    await page.goto('/'); await page.waitForLoadState('networkidle');
    await open(page, 'Organisation sections', 'Projects'); await page.getByRole('link', { name: 'Northwind Handbook' }).click();
    await open(page, 'Project sections', 'Agents'); await page.getByText('Budget exhausted').waitFor({ timeout: 15000 }); await shot('60-agents-budget-exhausted');
  });
  await step('dark', page, async () => {
    const dctx = await browser.newContext({ ...opts, colorScheme: 'dark' }); const d = await dctx.newPage();
    await d.request.post('/api/auth/sign-in', { data: OWNER }); await d.goto('/'); await d.waitForLoadState('networkidle');
    await open(d, 'Organisation sections', 'Projects'); await d.getByRole('link', { name: 'Northwind Handbook' }).click();
    await d.getByRole('table', { name: 'Documents' }).waitFor({ timeout: 15000 }); await shot('61-documents-dark', d);
    await open(d, 'Organisation sections', 'Cost'); await d.getByRole('table', { name: 'Cost by Project' }).getByRole('row').nth(1).waitFor({ timeout: 15000 }); await shot('62-cost-dark', d);
    await dctx.close();
  });
  await browser.close();
})();
