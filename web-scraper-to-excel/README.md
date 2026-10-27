# Web Scraper to Excel

A clean, production-style Python scraper that walks through every page of a listing site, cleans and de-duplicates the data, and exports a ready-to-use Excel workbook.

The demo target is [books.toscrape.com](https://books.toscrape.com), a public sandbox site built for scraping practice, so you can run it right away.

## What problem it solves

Copying product, directory or listing data by hand is slow and error-prone. This tool:

- follows pagination automatically (or stops after `--max-pages`)
- cleans text (whitespace, currency symbols, encoding artefacts) and converts prices/ratings to real numbers
- removes duplicates by URL
- retries on temporary errors (429/5xx) and waits between requests to be polite to the server
- writes a formatted `.xlsx`: bold coloured header, auto-fitted column widths, frozen first row, filter enabled, plus a **Summary** sheet

## Output example

A full run collects **1,000 books from 50 pages** in about 30 seconds. The generated file is included: [`output/books.xlsx`](output/books.xlsx).

![Excel output preview](docs/preview.png)

| Column | Example |
|---|---|
| Title | A Light in the Attic |
| Price (GBP) | 51.77 |
| Rating (1-5) | 3 |
| In Stock | Yes |
| Product URL / Image URL | absolute links |
| Source Page | 1 |

Summary sheet (from the included run): 1,000 books, average price £35.07, 196 five-star books.

## Install and run

Requires Python 3.9+.

```bash
pip install -r requirements.txt
python scraper.py                    # all pages -> output/books.xlsx
python scraper.py --max-pages 3      # quick test
python scraper.py --out data/books.xlsx --delay 1.0
```

Run the offline tests (no network needed):

```bash
python -m unittest -v
```

## Adapting it to your site

The code is split into small functions, so only the site-specific parts change:

1. **`START_URL`** - the first listing page.
2. **`parse_page()`** - the CSS selectors for each record (`article.product_pod`, `h3 a`, ...). Add or remove fields here and in the `Book` dataclass.
3. **`next_page_url()`** - how to find the "next" link (or build page URLs like `?page=2`).
4. **`HEADERS`** - the column names you want in Excel.

Typical extensions: login sessions, visiting each detail page for extra fields, CSV/Google Sheets output, scheduling, or switching to Playwright for JavaScript-heavy sites.

Please scrape responsibly: check the target site's terms and `robots.txt`, and keep a reasonable delay between requests.

## Project structure

```
scraper.py            # scraper + cleaning + Excel export (CLI)
tests/test_scraper.py # offline unit tests
output/books.xlsx     # sample output from a full run
docs/preview.png      # screenshot of the output
```

## License

MIT
