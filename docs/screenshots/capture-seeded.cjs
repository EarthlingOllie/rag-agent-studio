const { chromium } = require('playwright');
const OUT = process.argv[2] ?? __dirname, B = 'http://localhost:5173';
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, baseURL: B });
  const page = await ctx.newPage();
  const shot = async (n, full = false) => { await page.waitForTimeout(800); await page.screenshot({ path: `${OUT}/${n}.png`, fullPage: full }); console.log('shot', n); };
  const step = async (name, fn) => { try { await fn(); } catch (e) { console.log('FAIL', name, e.message.split('\n')[0]); await page.screenshot({ path: `${OUT}/fail-${name}.png` }); } };
  await page.request.post('/api/auth/sign-in', { data: { email: 'owner@northwind.example', password: 'northwind-owner-demo' } });
  await page.goto('/'); await page.waitForLoadState('networkidle');
  const nav = (n) => page.getByRole('navigation', { name: 'Project' }).getByRole('link', { name: n }).click();

  await step('projects', async () => {
    await page.getByRole('navigation', { name: 'Organisation' }).getByRole('link', { name: 'Projects' }).click();
    await page.getByRole('link', { name: 'Northwind Handbook' }).waitFor(); await shot('14-projects-seeded');
    await page.getByRole('link', { name: 'Northwind Handbook' }).click();
    const docs = page.getByRole('table', { name: 'Documents' });
    await docs.getByRole('cell', { name: 'Ready' }).nth(3).waitFor({ timeout: 120000 });
    await shot('15-documents-seeded', true);
  });
  await step('viewer', async () => {
    await page.getByRole('link', { name: 'northwind-staff-handbook.md' }).click();
    await page.getByRole('region', { name: 'Converted markdown' }).waitFor();
    await shot('16-document-viewer');
    await page.goBack(); await page.waitForLoadState('networkidle');
  });
  await step('instructions', async () => {
    await nav('Instructions'); await page.waitForLoadState('networkidle'); await shot('17-instructions', true);
    const pub = page.getByRole('form', { name: 'Publish Instructions' });
    for (const note of ['First version', 'Friendlier tone']) {
      await pub.getByRole('textbox', { name: 'Note' }).fill(note);
      if (note !== 'First version') {
        await page.getByRole('button', { name: 'Markdown' }).click().catch(() => {});
        const src = page.getByRole('textbox', { name: 'Project Instructions (Markdown)' });
        await src.fill((await src.inputValue()) + '\n\nAlways be warm and concise.');
      }
      await pub.getByRole('button', { name: 'Publish Instructions' }).click();
      await page.waitForTimeout(1500);
    }
    await page.getByText(/Current Version: v2/).waitFor({ timeout: 15000 });
    await shot('18-instructions-versions', true);
  });
  await step('agents', async () => {
    await nav('Agents'); await page.getByRole('link', { name: 'HR helper' }).waitFor(); await shot('19-agents-list');
    await page.getByRole('link', { name: 'HR helper' }).click();
    await page.getByRole('group', { name: 'Behaviour' }).waitFor({ timeout: 15000 });
    await shot('20-agent-config', true);
    await page.getByLabel('Question', { exact: true }).fill('How many days of annual leave do I get?');
    await page.getByRole('button', { name: 'Send' }).click();
    const answer = page.getByRole('list', { name: 'Playground messages' }).getByRole('listitem').last();
    await answer.getByRole('list', { name: 'Sources' }).waitFor({ timeout: 20000 });
    await answer.scrollIntoViewIfNeeded(); await shot('21-playground-citations');
    await answer.getByRole('button', { name: 'Trace' }).click();
    await page.getByRole('dialog', { name: 'Trace' }).getByText(/ms in all/).waitFor({ timeout: 15000 });
    await shot('22-trace-drawer');
    await page.keyboard.press('Escape');
  });
  const me = await (await page.request.get('/api/auth/me')).json(); const oid = me.organisations[0].id;
  for (const [n, p] of [['23-models-demo', '/models'], ['24-theme-seeded', '/theme'], ['25-credentials-seeded', '/credentials'], ['26-members-seeded', '/members'], ['27-audit-seeded', '/audit']])
    await step(n, async () => { await page.goto(`/organisations/${oid}/settings${p}`); await page.waitForLoadState('networkidle'); await shot(n); });
  await browser.close();
})();
