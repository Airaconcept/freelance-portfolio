// Static checks on the HTML - no browser needed.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const SITE = path.join(__dirname, '..', 'site');
const html = fs.readFileSync(path.join(SITE, 'index.html'), 'utf8');

test('has the basics for SEO and mobile', () => {
  assert.match(html, /<html lang="en">/);
  assert.match(html, /<meta name="viewport" content="width=device-width, initial-scale=1">/);
  assert.match(html, /<title>[^<]{10,}<\/title>/);
  assert.match(html, /<meta name="description" content="[^"]{50,}">/);
  assert.strictEqual((html.match(/<h1[\s>]/g) || []).length, 1);
});

test('every in-page link points to an existing id', () => {
  const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
  const targets = [...html.matchAll(/href="#([^"]*)"/g)].map((m) => m[1]);
  assert.ok(targets.length > 10);
  for (const t of targets) assert.ok(ids.has(t), `missing #${t}`);
});

test('local assets exist and nothing is loaded from other sites', () => {
  for (const m of html.matchAll(/(?:src|href)="([^"#][^"]*)"/g)) {
    assert.ok(!/^(https?:)?\/\//.test(m[1]), `external resource: ${m[1]}`);
    assert.ok(fs.existsSync(path.join(SITE, m[1])), `missing file: ${m[1]}`);
  }
});

test('images have alt text, form fields have labels', () => {
  for (const m of html.matchAll(/<img\b[^>]*>/g)) assert.match(m[0], /\salt="/);
  for (const m of html.matchAll(/<(?:input|select|textarea)\b[^>]*\sid="([^"]+)"/g)) {
    assert.match(html, new RegExp(`<label for="${m[1]}"`), `no label for #${m[1]}`);
  }
});

test('no real contact details are published (placeholder form only)', () => {
  assert.doesNotMatch(html, /mailto:|tel:|wa\.me|t\.me\/|wechat/i);
  const emails = [...html.matchAll(/[\w.+-]+@[\w-]+\.[\w.]+/g)].map((m) => m[0]);
  assert.deepStrictEqual(emails.filter((e) => !e.endsWith('@example.com')), []);
  assert.match(html, /<form id="contact-form"[^>]*action="#"/);
});

test('no inline styles or scripts, so the strict CSP in site/_headers works', () => {
  assert.doesNotMatch(html, /\sstyle="/);
  assert.doesNotMatch(html, /<style[\s>]/);
  assert.doesNotMatch(html, /\son[a-z]+="/);                      // onclick= etc.
  for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
    assert.match(m[1], /\ssrc="/); assert.strictEqual(m[2].trim(), '');
  }
});
