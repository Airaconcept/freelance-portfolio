// Render the page in headless Chromium at desktop and mobile sizes -> docs/*.png
const path = require('path');
const { createServer } = require('./serve');
const { launch } = require('./browser');

(async () => {
  const server = createServer();
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const url = `http://127.0.0.1:${server.address().port}/`;
  const browser = await launch();
  try {
    const shots = [
      { name: 'desktop.png', viewport: { width: 1280, height: 800 }, fullPage: true },
      { name: 'desktop-hero.png', viewport: { width: 1280, height: 800 }, fullPage: false },
      { name: 'mobile.png', viewport: { width: 390, height: 844 }, fullPage: true, mobile: true },
      { name: 'mobile-menu.png', viewport: { width: 390, height: 844 }, fullPage: false, mobile: true, openMenu: true },
    ];
    for (const s of shots) {
      const ctx = await browser.newContext({ viewport: s.viewport, deviceScaleFactor: s.mobile ? 2 : 1, isMobile: !!s.mobile, hasTouch: !!s.mobile });
      const page = await ctx.newPage();
      await page.goto(url, { waitUntil: 'load' });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      if (s.openMenu) await page.click('.nav-toggle');
      await page.screenshot({ path: path.join(__dirname, 'docs', s.name), fullPage: s.fullPage });
      console.log('docs/' + s.name);
      await ctx.close();
    }
  } finally {
    await browser.close();
    server.close();
  }
})().catch((e) => { console.error(e); process.exit(1); });
