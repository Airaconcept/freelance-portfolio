# Landing Page Site - responsive single page, plain HTML/CSS/JS

A clean, fast, responsive landing page built **without frameworks**: one HTML file, one stylesheet, under 50 lines of JavaScript. No external scripts, fonts or trackers. Includes a validated contact form (placeholder - not connected), automated browser tests, screenshots, and ready-to-use deployment setups for **Cloudflare Pages** and **GitHub Pages**.

The product on the page, "Ledgerly", is **fictional** - a stand-in to show the template. All names, figures and prices are placeholders.

## What problem it solves

Small businesses, freelancers and new products need a page that loads instantly, looks right on every phone, and is easy to edit and host for free. This template gives you:

- **sections that sell**: hero with call-to-action, features, how-it-works steps, pricing table, FAQ (native `<details>`, no JS), contact form, footer
- **responsive layout** with CSS Grid: 4 -> 2 -> 1 columns; a hamburger menu under 760 px (keyboard accessible, `aria-expanded`)
- **accessibility basics**: skip link, labelled form fields, visible focus outlines, `prefers-reduced-motion` support, error messages announced with `aria-live`
- **SEO basics**: title, meta description, Open Graph tags, one `<h1>`, semantic sections
- **contact form** with client-side validation and a clear demo confirmation; swapping in a real endpoint is a few lines (see below)
- **security headers** for Cloudflare Pages (`site/_headers`) including a strict Content-Security-Policy - the page has no inline styles or scripts, so it works under `default-src 'self'`
- **total size about 22 KB** (HTML + CSS + JS + icon), nothing loaded from other sites

## Screenshots

Rendered with headless Chromium by `npm run screenshots`:

![Desktop and mobile preview](docs/preview.png)

Full pages: [desktop](docs/desktop.png) - [mobile](docs/mobile.png) - [mobile menu open](docs/mobile-menu.png)

## Run it locally

Open `site/index.html` directly in a browser, or serve it (Node.js 18+, no dependencies):

```bash
npm start                  # http://localhost:8080 (also sends the headers from site/_headers)
```

### Tests

```bash
npm install                        # installs Playwright (dev dependency)
npx playwright install chromium    # or use an installed Chrome/Chromium, see below
npm test
```

- `test/static.test.js` (no browser): viewport/SEO tags, every `#anchor` has a target, local files exist and nothing is loaded from other sites, images have `alt`, inputs have labels, no real contact details are published, no inline styles/scripts (CSP-safe)
- `test/browser.test.js` (headless Chromium, local server, no internet): no horizontal scrolling and no console/JS/CSP errors at 360, 768, 1280 and 1920 px; mobile menu opens/closes; form shows errors for empty and invalid input and the confirmation for valid input

Where Playwright's own Chromium cannot be downloaded (e.g. ARM64 Linux), set `CHROMIUM_PATH=/usr/bin/chromium` or install a system Chromium - `browser.js` falls back to it automatically. The included screenshots and test runs were made that way.

## Deploy

The deployable site is only the `site/` folder. Both options below are free for a site like this.

### Cloudflare Pages

**Dashboard (no tools needed)**
1. Cloudflare dashboard -> **Workers & Pages** -> **Create** -> **Pages** -> **Upload assets**.
2. Name the project (it becomes `<name>.pages.dev`), drag in the **contents of `site/`**, click **Deploy site**.
3. Optional: **Custom domains** -> add your domain.

**Command line**
```bash
npx wrangler login
npx wrangler pages deploy site --project-name=my-landing-page
```

**From a Git repository**: Workers & Pages -> Create -> Pages -> **Connect to Git**, pick the repo, framework preset **None**, build command empty, **build output directory** `landing-page-site/site` (or `site` if the page is the repo root). Every push then redeploys automatically.

`site/_headers` is applied automatically by Cloudflare Pages.

### GitHub Pages

**Simplest (page in its own repository)**: put the contents of `site/` in the repo root -> **Settings -> Pages** -> Source **Deploy from a branch** -> `main` / `(root)` -> Save. The site appears at `https://<user>.github.io/<repo>/`.

**From a sub-folder (like this repo)**: copy [`deploy/github-pages.yml`](deploy/github-pages.yml) to `.github/workflows/pages.yml`, set `SITE_DIR`, then **Settings -> Pages** -> Source **GitHub Actions**. Each push to `main` that touches the site publishes it.

GitHub Pages does not read `_headers`; if you need the security headers there, put Cloudflare in front or use Cloudflare Pages.

## Adapting it

1. **Texts, prices, sections** - all in `site/index.html`; delete a `<section>` you do not need and its menu link (the tests will tell you if a link points nowhere).
2. **Colours and fonts** - the variables at the top of `site/styles.css` (`--blue`, `--ink`, ...). The page uses the system font stack; to add a web font, self-host it in `site/` to keep the CSP.
3. **Logo** - replace `site/favicon.svg` (used as logo and browser icon).
4. **Connect the form** - in `site/script.js`, replace the block marked `DEMO ONLY` with a `fetch()` to your endpoint, for example a form service (Formspree, Basin, Web3Forms), Netlify Forms, or a Cloudflare Pages Function / Worker that e-mails you or writes to a sheet. Add that endpoint's origin to `form-action` / `connect-src` in `site/_headers`.
5. **Analytics** - a privacy-friendly option such as Cloudflare Web Analytics can be enabled in the Pages project without touching the code.

## Project structure

```
site/                     # the deployable website
  index.html  styles.css  script.js  favicon.svg  _headers
serve.js                  # zero-dependency local server (applies _headers)
screenshots.js            # desktop/mobile screenshots -> docs/
browser.js                # Chromium launcher (Playwright build or system Chromium)
test/                     # static + headless-browser tests
deploy/github-pages.yml   # GitHub Actions workflow for GitHub Pages
docs/                     # screenshots
```

## License

MIT
