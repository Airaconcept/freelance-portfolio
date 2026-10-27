# AI Text Extractor - unstructured text -> structured Excel with an LLM

Turns free-form documents - **invoices, e-mails, order requests, complaints** - into clean rows in **Excel** using a large language model, and **checks the answer** before it goes into the spreadsheet. Works with any **OpenAI-compatible API** (OpenAI, DeepSeek, OpenRouter, Groq, a local Ollama or LM Studio...). A built-in **rules backend** runs the whole pipeline offline, without an API key.

All sample documents in [`samples/`](samples/) are **invented demo data** (fictional companies and people).

## What problem it solves

Teams re-type the same information every day: invoice numbers and totals into accounting sheets, customer requests into a CRM or ticket list. Every supplier and every customer writes differently, so templates and regexes break. An LLM reads them all - but its answers have to be checked. This tool:

- defines the fields **once** in [`schema.py`](schema.py); the same definition writes the prompt, converts the answer and builds the Excel columns
- asks the model for **JSON only** (`response_format: json_object` where supported, `temperature: 0`)
- **parses robustly**: plain JSON, ```json fenced blocks, or JSON wrapped in text; if the answer is not valid JSON it asks the model again and says what was wrong
- **retries** 429/5xx and network errors; falls back automatically if a server does not support JSON mode; fails fast on auth errors
- **normalises** values: `"£309.60"` -> `309.6`, `"3 Oct 2026"` -> `2026-10-03`, enum values checked
- **verifies the business logic**: quantity x unit price = line amount, line items = subtotal, subtotal + tax = total, due date not before invoice date, required fields present
- writes everything doubtful to a **Review** sheet and highlights the row, instead of silently storing a wrong number
- one bad document never stops the batch

## Output example

[`output/extracted.xlsx`](output/extracted.xlsx) (+ [`output/extracted.json`](output/extracted.json)) - sheets **Invoices**, **Line Items**, **Emails**, **Review**.

![Output preview](docs/preview.png)

The included output was produced with the offline **rules backend** (`--backend rules`), so it can be reproduced without an API key; with an LLM backend the same sheets are produced, and the `summary` column is filled too. Expected values for every sample, checked by hand against the texts, are in [`expected/`](expected/).

| Document | Extracted |
|---|---|
| `invoice_02.txt` (bullet-style bill, EUR) | vendor *Placeholder Print Studio*, number *PPS-0932*, 2026-09-15 / due 2026-09-29, 205.00 + 38.95 = 243.95 EUR, 3 line items |
| `email_02.txt` (complaint) | intent *complaint*, reference *77812*, items *4 boxes of paper cups*, urgency *high* |

## Install and run

Requires Python 3.9+.

```bash
pip install -r requirements.txt

# offline demo, no key needed
python extract.py "samples/*.txt" --backend rules -o output/extracted.xlsx --json output/extracted.json

# with an LLM: copy .env.example to .env and fill in, or export the variables
export LLM_API_KEY=...                      # LLM_BASE_URL / LLM_MODEL optional
python extract.py "samples/*.txt" -o output/extracted.xlsx
python extract.py "inbox/*.txt" --model gpt-4o -o out.xlsx
```

| Provider | `LLM_BASE_URL` | Key needed |
|---|---|---|
| OpenAI (default) | `https://api.openai.com/v1` | yes |
| DeepSeek | `https://api.deepseek.com/v1` | yes |
| OpenRouter | `https://openrouter.ai/api/v1` | yes |
| Ollama (local) | `http://localhost:11434/v1` | no |
| LM Studio (local) | `http://localhost:1234/v1` | no |

A local model keeps documents on your own machine - useful for confidential invoices.

### Tests (offline, no key)

```bash
python -m unittest -v
```

- the rules backend is compared field by field with [`expected/`](expected/)
- the OpenAI-compatible backend is tested against a **local fake server** that imitates `/v1/chat/completions`: request format (auth header, model, JSON mode, schema in the prompt), fenced/invalid JSON with re-ask, 503 retry, JSON-mode fallback, no retry on 401, and an end-to-end run where a wrong total is flagged in the Review sheet

## Adapting it to your documents

1. **Fields** - edit [`schema.py`](schema.py): add a document type (e.g. `purchase_order`, `cv`, `contract`) or fields (`iban`, `po_number`, `delivery_address`). Types: `string`, `number`, `date`, `enum:a|b|c`.
2. **Checks** - add your own rules in `check()` in `extract.py` (e.g. VAT rate must be 19 %, vendor must be in a supplier list).
3. **Input** - PDFs and scans: extract the text first (`pdfplumber`, or OCR with Tesseract; see the `pdf-table-to-excel` sample), then pass it in. E-mails: read them from an IMAP mailbox or `.eml` files.
4. **Output** - the results are plain dicts; write them to Google Sheets, a database or a CRM API instead of / in addition to Excel.
5. **Cost** - one request per document; small models (e.g. `gpt-4o-mini`, `deepseek-chat`) are usually enough for this kind of extraction.

## Project structure

```
extract.py           # CLI: read -> extract -> normalise -> check -> Excel/JSON
backends.py          # OpenAI-compatible backend + offline rules backend
schema.py            # the fields to extract (drives prompt, validation and columns)
samples/             # invented invoices and e-mails
expected/            # hand-checked expected results for the samples
output/              # extracted.xlsx + extracted.json from the rules backend
tests/               # offline tests with a fake OpenAI-compatible server
.env.example         # LLM settings template
```

## License

MIT
