#!/usr/bin/env node
// Scrape a JavaScript-rendered listing with Playwright and export JSON + CSV.
//
//   node scrape.js                                   # https://quotes.toscrape.com/js/ , all pages
//   node scrape.js --max-pages 3 --out output
//   node scrape.js --url https://quotes.toscrape.com/js/ --screenshot docs/page1.png
//
// The quotes on the demo page do not exist in the HTML source - they are inserted by JavaScript,
// so requests/BeautifulSoup see nothing. A real browser renders the page, then we read the DOM.
const { chromium } = require('playwright');
const { launchBrowser, normaliseQuote, dedupe, writeOutputs } = require('./lib');

// ---- site-specific part: change these for another site --------------------------------------
const SELECTORS = {
  item: '.quote',
  text: '.text',
  author: '.author',
  tags: '.tags .tag',
  next: 'li.next a',
};

function parseArgs(argv) {
  const a = { url: 'https://quotes.toscrape.com/js/', maxPages: Infinity, out: 'output', delay: 500, screenshot: null };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i], v = argv[i + 1];
    if (k === '--url') { a.url = v; i++; }
    else if (k === '--max-pages') { a.maxPages = Number(v); i++; }
    else if (k === '--out') { a.out = v; i++; }
    else if (k === '--delay') { a.delay = Number(v); i++; }
    else if (k === '--screenshot') { a.screenshot = v; i++; }
    else if (k === '--help' || k === '-h') { console.log('usage: node scrape.js [--url U] [--max-pages N] [--out DIR] [--delay MS] [--screenshot FILE]'); process.exit(0); }
  }
  return a;
}

async function scrape({ url, maxPages = Infinity, delay = 500, screenshot = null, log = console.log }) {
  const browser = await launchBrowser(chromium);
  const page = await browser.newPage({ userAgent: 'Mozilla/5.0 (portfolio sample; Playwright)' });
  const results = [];
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    for (let pageNo = 1; pageNo <= maxPages; pageNo++) {
      await page.waitForSelector(SELECTORS.item, { timeout: 15000 }); // wait for JS to render the items
      if (screenshot && pageNo === 1) await page.screenshot({ path: screenshot, fullPage: false });
      const raw = await page.$$eval(SELECTORS.item, (nodes, s) => nodes.map((n) => ({
        text: n.querySelector(s.text)?.textContent,
        author: n.querySelector(s.author)?.textContent,
        tags: [...n.querySelectorAll(s.tags)].map((t) => t.textContent),
      })), SELECTORS);
      results.push(...raw.map((r) => normaliseQuote(r, pageNo)));
      log(`page ${pageNo}: ${raw.length} items (${page.url()})`);

      const next = await page.$(SELECTORS.next);
      if (!next || pageNo === maxPages) break;
      const firstText = raw[0]?.text;
      await Promise.all([page.waitForLoadState('domcontentloaded'), next.click()]);
      // make sure the new page's items replaced the old ones before reading again
      await page.waitForFunction(
        ([sel, old]) => { const el = document.querySelector(sel); return el && el.textContent !== old; },
        [`${SELECTORS.item} ${SELECTORS.text}`, firstText], { timeout: 15000 });
      if (delay) await page.waitForTimeout(delay); // be polite to the server
    }
  } finally {
    await browser.close();
  }
  return dedupe(results);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const t0 = Date.now();
  const items = await scrape(args);
  const { jsonPath, csvPath } = writeOutputs(items, args.out);
  const authors = new Set(items.map((i) => i.author)).size;
  console.log(`${items.length} quotes by ${authors} authors in ${((Date.now() - t0) / 1000).toFixed(1)}s -> ${jsonPath}, ${csvPath}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(e.message); process.exit(1); });
}

module.exports = { scrape, SELECTORS };
