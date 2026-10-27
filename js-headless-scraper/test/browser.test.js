// End-to-end test with a real headless browser against a LOCAL fixture site (no internet needed).
// The fixture renders its items with JavaScript and has 2 pages, like the demo target.
// Skipped (not failed) only if no Chromium can be launched on this machine.
const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
const { launchBrowser, writeOutputs } = require('../lib');
const { scrape } = require('../scrape');

const html = fs.readFileSync(path.join(__dirname, 'fixtures', 'page.html'));

async function browserAvailable() {
  try { const b = await launchBrowser(chromium); await b.close(); return true; } catch { return false; }
}

test('scrapes JS-rendered items across pages, de-duplicates, writes JSON + CSV', async (t) => {
  if (!(await browserAvailable())) return t.skip('no Chromium available (run: npx playwright install chromium)');
  const server = http.createServer((req, res) => { res.writeHead(200, { 'content-type': 'text/html' }); res.end(html); });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const url = `http://127.0.0.1:${server.address().port}/`;
  try {
    const logs = [];
    const items = await scrape({ url, delay: 0, log: (m) => logs.push(m) });
    assert.strictEqual(logs.length, 2);                       // followed the "Next" link once
    assert.deepStrictEqual(items.map((i) => [i.author, i.page]),
      [['Ada Lovelace', 1], ['Alan Turing', 1], ['Grace Hopper', 2]]); // duplicate on page 2 removed
    assert.strictEqual(items[0].text, 'First quote, with a comma.');
    assert.strictEqual(items[1].text, 'He said "hi".');
    assert.deepStrictEqual(items[0].tags, ['math', 'code']);

    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'scrape-'));
    const { jsonPath, csvPath } = writeOutputs(items, dir);
    assert.strictEqual(JSON.parse(fs.readFileSync(jsonPath, 'utf8')).length, 3);
    assert.strictEqual(fs.readFileSync(csvPath, 'utf8').trim().split('\r\n').length, 4);

    const one = await scrape({ url, delay: 0, maxPages: 1, log: () => {} });
    assert.strictEqual(one.length, 2);                        // --max-pages respected
  } finally {
    server.close();
  }
});
