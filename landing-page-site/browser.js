// Launch Chromium via Playwright: Playwright's own build if installed, otherwise CHROMIUM_PATH or a system Chrome/Chromium.
const fs = require('fs');
const SYSTEM = ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'];

async function launch() {
  const { chromium } = require('playwright');
  const args = ['--no-sandbox', '--disable-dev-shm-usage'];
  if (process.env.CHROMIUM_PATH) return chromium.launch({ args, executablePath: process.env.CHROMIUM_PATH });
  try { return await chromium.launch({ args }); } catch (e) {
    const p = SYSTEM.find((x) => fs.existsSync(x));
    if (!p) throw e;
    return chromium.launch({ args, executablePath: p });
  }
}
module.exports = { launch };
