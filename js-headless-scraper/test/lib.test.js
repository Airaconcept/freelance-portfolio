// Unit tests - no browser, no network.  Run: npm test
const test = require('node:test');
const assert = require('node:assert');
const { cleanText, normaliseQuote, dedupe, toCsv, proxyFromEnv } = require('../lib');

test('cleanText normalises quotes and whitespace', () => {
  assert.strictEqual(cleanText('  \u201cHi\u201d \n  there\u2019s  '), '"Hi" there\'s');
  assert.strictEqual(cleanText(undefined), '');
});

test('normaliseQuote strips the outer quotation marks and cleans tags', () => {
  const q = normaliseQuote({ text: '\u201cBe yourself.\u201d', author: ' Oscar  Wilde ', tags: [' life ', ''] }, 3);
  assert.deepStrictEqual(q, { text: 'Be yourself.', author: 'Oscar Wilde', tags: ['life'], page: 3 });
});

test('dedupe keeps the first occurrence', () => {
  const items = [{ text: 'a', author: 'x', page: 1 }, { text: 'a', author: 'x', page: 2 }, { text: 'b', author: 'x', page: 2 }];
  assert.deepStrictEqual(dedupe(items).map((i) => i.page), [1, 2]);
});

test('toCsv escapes commas, quotes and joins tags; starts with a BOM for Excel', () => {
  const csv = toCsv([{ text: 'He said "hi", ok', author: 'A', tags: ['t1', 't2'], page: 1 }], ['text', 'author', 'tags', 'page']);
  assert.ok(csv.startsWith('\uFEFFtext,author,tags,page\r\n'));
  assert.ok(csv.includes('"He said ""hi"", ok",A,t1; t2,1'));
});

test('proxyFromEnv parses credentials for Chromium', () => {
  assert.strictEqual(proxyFromEnv({}), undefined);
  assert.deepStrictEqual(proxyFromEnv({ HTTPS_PROXY: 'http://user:p%40ss@proxy.local:8080', NO_PROXY: 'localhost, example.internal' }),
    { server: 'http://proxy.local:8080', username: 'user', password: 'p@ss', bypass: 'localhost,127.0.0.1,[::1],example.internal' });
});
