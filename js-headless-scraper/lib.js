// Browser-independent helpers: launching, cleaning, de-duplication, CSV/JSON output.
const fs = require('fs');
const path = require('path');

// Chromium locations used when Playwright's own browser is not installed
// (e.g. ARM Linux servers, Docker images that ship a distro Chromium).
const SYSTEM_CHROMIUM = [
  '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
];

// Use HTTPS_PROXY / HTTP_PROXY (incl. user:password) if set - Chromium itself ignores these variables.
function proxyFromEnv(env = process.env) {
  const raw = env.HTTPS_PROXY || env.https_proxy || env.HTTP_PROXY || env.http_proxy;
  if (!raw) return undefined;
  const u = new URL(raw.includes('://') ? raw : `http://${raw}`);
  const proxy = { server: `${u.protocol}//${u.hostname}${u.port ? ':' + u.port : ''}` };
  if (u.username) proxy.username = decodeURIComponent(u.username);
  if (u.password) proxy.password = decodeURIComponent(u.password);
  // Playwright proxies localhost too unless told otherwise; keep local addresses direct.
  const bypass = ['localhost', '127.0.0.1', '[::1]', ...String(env.NO_PROXY || env.no_proxy || '').split(',')]
    .map((s) => s.trim()).filter(Boolean);
  proxy.bypass = [...new Set(bypass)].join(',');
  return proxy;
}

async function launchBrowser(chromium, { headless = true } = {}) {
  const opts = { headless, args: ['--no-sandbox', '--disable-dev-shm-usage'], proxy: proxyFromEnv() };
  if (process.env.CHROMIUM_PATH) {
    return chromium.launch({ ...opts, executablePath: process.env.CHROMIUM_PATH });
  }
  try {
    return await chromium.launch(opts); // browser from `npx playwright install chromium`
  } catch (err) {
    const found = SYSTEM_CHROMIUM.find((p) => fs.existsSync(p));
    if (!found) throw err;
    return chromium.launch({ ...opts, executablePath: found });
  }
}

function cleanText(s) {
  return String(s ?? '')
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

function normaliseQuote(raw, pageNo) {
  let text = cleanText(raw.text);
  if (text.startsWith('"') && text.endsWith('"')) text = text.slice(1, -1).trim();
  return {
    text,
    author: cleanText(raw.author),
    tags: (raw.tags || []).map(cleanText).filter(Boolean),
    page: pageNo,
  };
}

function dedupe(items, key = (i) => `${i.text}|${i.author}`) {
  const seen = new Set();
  return items.filter((i) => {
    const k = key(i);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

function csvCell(v) {
  const s = Array.isArray(v) ? v.join('; ') : String(v ?? '');
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toCsv(items, columns) {
  const lines = [columns.join(',')];
  for (const i of items) lines.push(columns.map((c) => csvCell(i[c])).join(','));
  return '\uFEFF' + lines.join('\r\n') + '\r\n'; // BOM so Excel opens UTF-8 correctly
}

function writeOutputs(items, outDir, base = 'quotes') {
  fs.mkdirSync(outDir, { recursive: true });
  const jsonPath = path.join(outDir, `${base}.json`);
  const csvPath = path.join(outDir, `${base}.csv`);
  fs.writeFileSync(jsonPath, JSON.stringify(items, null, 2) + '\n');
  fs.writeFileSync(csvPath, toCsv(items, ['text', 'author', 'tags', 'page']));
  return { jsonPath, csvPath };
}

module.exports = { launchBrowser, proxyFromEnv, cleanText, normaliseQuote, dedupe, toCsv, writeOutputs };
