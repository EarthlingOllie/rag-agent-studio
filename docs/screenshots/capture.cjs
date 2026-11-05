const { chromium } = require('playwright');
const path = require('node:path');
const OUT = __dirname, B = process.env.E2E_BASE_URL ?? 'http://localhost:5173';
const HANDBOOK = path.join(__dirname, '../../seed/documents/northwind-staff-handbook.md');
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, baseURL: B });
  const page = await ctx.newPage();
  const shot = async (n) => { await page.waitForTimeout(800); await page.screenshot({ path: `${OUT}/${n}.png` }); console.log('shot', n); };
  const step = async (name, fn) => { try { await fn(); } catch (e) { console.log('FAIL', name, e.message.split('\n')[0]); await page.screenshot({ path: `${OUT}/fail-${name}.png` }); } };

  await page.goto('/sign-up'); await shot('01-sign-up');
  await page.goto('/sign-in'); await shot('02-sign-in');
  const m = { name: 'Ada Lovelace', email: 'ada@northwind.example', password: 'correct horse battery staple 1', organisation_name: 'Northwind Traders' };
  let r = await page.request.post('/api/auth/sign-up', { data: m }); console.log('signup', r.status());
  r = await page.request.post('/api/auth/sign-in', { data: { email: m.email, password: m.password } }); console.log('signin', r.status());
  await page.goto('/'); await page.waitForLoadState('networkidle');
  const me = await (await page.request.get('/api/auth/me')).json();
  const org = `/api/organisations/${me.organisations[0].id}`;
  const cred = await (await page.request.post(`${org}/credentials`, { data: { name: 'Support Claude', provider: 'anthropic', api_key: 'sk-ant-demo-not-a-real-key-p9q2' } })).json();
  await page.request.put(`${org}/default-model`, { data: { credential_id: cred.id, model: 'claude-haiku-4-5' } });

  await step('projects', async () => {
    await page.getByRole('navigation', { name: 'Organisation' }).getByRole('link', { name: 'Projects' }).click();
    await shot('03-projects-empty');
    const f = page.getByRole('form', { name: 'New Project' });
    await f.getByLabel('Name').fill('Northwind HR');
    await f.getByRole('button', { name: 'Create Project' }).click();
    await page.getByLabel('Choose files to upload').setInputFiles(HANDBOOK);
    const row = page.getByRole('table', { name: 'Documents' }).getByRole('row', { name: /northwind-staff-handbook\.md/ });
    await row.getByRole('cell', { name: 'Ready' }).waitFor({ timeout: 60000 });
    await shot('04-documents');
  });
  await step('agent', async () => {
    await page.getByRole('navigation', { name: 'Project' }).getByRole('link', { name: 'Agents' }).click();
    await page.getByText(/No Agents yet/).waitFor({ timeout: 15000 });
    const f = page.getByRole('form', { name: 'New Agent' });
    await f.getByLabel('Name').fill('HR helper');
    await f.getByRole('button', { name: 'Create Agent' }).click();
    await page.getByRole('heading', { level: 2, name: 'HR helper' }).waitFor({ timeout: 15000 });
    await page.getByLabel('System prompt').fill('You answer Northwind staff questions about HR policy, citing the handbook.');
    await page.getByRole('button', { name: 'Save Draft' }).click();
    await page.getByText('Draft saved').waitFor({ timeout: 15000 });
    await page.getByLabel('Question').fill('How many days of annual leave do I get?');
    await page.getByRole('button', { name: 'Send' }).click();
    await page.getByRole('list', { name: 'Playground messages' }).getByRole('listitem', { name: 'HR helper' }).getByText(/output tokens/).waitFor({ timeout: 20000 });
    await shot('06-agent-playground');
  });
  const oid = me.organisations[0].id;
  for (const [n, p] of [['07-settings-general', ''], ['08-members', '/members'], ['09-credentials', '/credentials'], ['10-models', '/models'], ['11-theme', '/theme'], ['12-audit', '/audit']]) {
    await step(n, async () => { await page.goto(`/organisations/${oid}/settings${p}`); await page.waitForLoadState('networkidle'); await shot(n); });
  }
  await step('profile', async () => { await page.goto(`/organisations/${oid}/profile`); await page.waitForLoadState('networkidle'); await shot('13-profile'); });
  await browser.close();
})();
