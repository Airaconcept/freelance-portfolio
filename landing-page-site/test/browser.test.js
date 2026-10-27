// Headless-browser checks: layout at several widths, mobile menu, form validation.
// Uses a local server - no internet needed. Skipped if no Chromium can be launched.
const test = require('node:test');
const assert = require('node:assert');
const { createServer } = require('../serve');
const { launch } = require('../browser');

let browser, server, url;

test.before(async () => {
  server = createServer();
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  url = `http://127.0.0.1:${server.address().port}/`;
  try { browser = await launch(); } catch { browser = null; }
});
test.after(async () => { if (browser) await browser.close(); server.close(); });

for (const width of [360, 768, 1280, 1920]) {
  test(`no horizontal scrolling and no JS errors at ${width}px`, async (t) => {
    if (!browser) return t.skip('no Chromium available');
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); }); // incl. CSP violations
    await page.goto(url);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert.ok(overflow <= 0, `page is ${overflow}px wider than the viewport`);
    assert.deepStrictEqual(errors, []);
    await page.close();
  });
}

test('local server sends the CSP from site/_headers', async () => {
  const res = await fetch(url);
  assert.match(res.headers.get('content-security-policy') || '', /default-src 'self'/);
});

test('mobile menu opens and closes', async (t) => {
  if (!browser) return t.skip('no Chromium available');
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.goto(url);
  assert.strictEqual(await page.isVisible('#nav-menu'), false);
  await page.click('.nav-toggle');
  assert.strictEqual(await page.isVisible('#nav-menu'), true);
  assert.strictEqual(await page.getAttribute('.nav-toggle', 'aria-expanded'), 'true');
  await page.click('#nav-menu a[href="#pricing"]');           // choosing a link closes the menu
  assert.strictEqual(await page.isVisible('#nav-menu'), false);
  await page.close();
});

test('contact form validates and shows the demo confirmation', async (t) => {
  if (!browser) return t.skip('no Chromium available');
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(url);
  await page.click('#contact-form button[type=submit]');
  assert.strictEqual(await page.getAttribute('#name', 'aria-invalid'), 'true');
  assert.match(await page.textContent('#email + .error'), /enter your email/);
  assert.strictEqual(await page.evaluate(() => document.activeElement.id), 'name');

  await page.fill('#name', 'Jane Doe');
  await page.fill('#email', 'not-an-email');
  await page.click('#contact-form button[type=submit]');
  assert.match(await page.textContent('#email + .error'), /valid email/);

  await page.fill('#email', 'jane@example.com');
  await page.click('#contact-form button[type=submit]');
  assert.match(await page.textContent('.form-status'), /Thanks, Jane! \(Demo/);
  assert.strictEqual(await page.inputValue('#name'), '');       // form reset
  await page.close();
});
