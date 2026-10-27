# Automation Workflow: RSS + Web Page Monitor -> Daily Digest

A config-driven automation that checks RSS feeds and web pages, keeps **only what is new since the last run**, and produces a daily report in **Markdown and Excel**, with optional push to **Slack, Discord or any webhook**.

It ships in two equivalent forms:

- `digest.py` - a plain Python script you can schedule with cron / Task Scheduler
- `n8n/daily-digest-workflow.json` - the same flow as an [n8n](https://n8n.io) workflow you can import

## What problem it solves

Following several blogs, news feeds, competitor pages or job boards by hand takes time every day, and it is easy to miss changes. This workflow:

- reads any number of **RSS/Atom feeds**
- watches **web pages without a feed**: give it a URL and a CSS selector, and new or changed entries are reported
- remembers what was already reported (`state/seen.json`), so each digest only contains new items
- optional **keyword filter** (e.g. only titles containing "python" or "pricing")
- one broken source never stops the report; errors are listed at the end of the digest
- writes `reports/digest-YYYY-MM-DD_HHMM.md` and `.xlsx`
- optional **webhook** push: Slack (`text`), Discord (`content`) or generic JSON with all items

Everything is controlled from [`config.yaml`](config.yaml) - no code changes for new sources.

## Output example

From a real run (4 sources, 50 new items): [`examples/sample-digest.md`](examples/sample-digest.md) and [`examples/sample-digest.xlsx`](examples/sample-digest.xlsx).

![Excel output preview](docs/preview.png)

```markdown
# Daily Tech Digest - 2026-10-27

Generated 2026-10-27 12:19 UTC. **50 new item(s)** from 4 source(s).

## Python Insider (15 new / 15 checked)

- [Python 3.15.2, 3.14.10, 3.13.18, 3.12.16 and 3.11.18 are out](https://blog.python.org/...)
...
```

Running it again right away reports `0 new item(s)` - only changes are sent.

## Install and run (Python)

Requires Python 3.9+.

```bash
pip install -r requirements.txt
python digest.py              # build today's digest
python digest.py --dry-run    # build it and print the webhook payload without sending
python digest.py --reset      # forget what was seen
```

Turn on the webhook in `config.yaml` (`webhook.enabled: true`) and put the URL there or in the environment variable `DIGEST_WEBHOOK_URL` (recommended, keeps secrets out of the file).

Schedule it daily at 08:00 (Linux/macOS):

```
0 8 * * *  cd /path/to/automation-workflow && /usr/bin/python3 digest.py
```

Run the tests (offline: a local test server plays the feed, the web page and the webhook receiver; also validates the n8n JSON):

```bash
python -m unittest -v
```

## Import into n8n

1. In n8n: **Workflows -> Import from File** -> choose `n8n/daily-digest-workflow.json`.
2. Edit the **Feed List** node (one line per feed) and, for page monitoring, the URL in **Fetch Web Page** and the CSS selector in **Extract Watched Elements**.
3. Put your Slack/Discord/webhook URL in **Send to Webhook** (for Discord, change `text` to `content` in the JSON body).
4. Activate the workflow. It runs every day at 08:00 (**Every Day 08:00** node).

Flow:

```
Every Day 08:00 -+-> Feed List -> Read RSS -> Normalize Feed Items ------------+
                 |                                                              +-> Merge Sources -> New Items + Markdown Digest -> Anything New? -> Send to Webhook
                 +-> Fetch Web Page -> Extract Watched Elements -> Normalize Page Items -+
```

Notes: "already seen" memory uses n8n workflow static data, which is saved for active (production) executions, not for manual test runs. Failed sources are skipped (`On Error: Continue`) so the digest still goes out. The JSON's structure and every Code node's JavaScript are checked by the test suite; it targets current n8n 1.x node versions.

## Adapting it

- **Different sources**: edit `sources:` in `config.yaml` (`type: rss` or `type: web` with `selector`).
- **Other outputs**: e-mail (SMTP), Telegram, Google Sheets or Notion are a small addition next to `webhook_payload()`.
- **Smarter digests**: add AI summaries per item, grouping by topic, or price/stock thresholds for e-commerce pages.
- **Hosting**: runs anywhere Python runs (VPS, GitHub Actions schedule, Raspberry Pi), or fully inside n8n.

## Project structure

```
digest.py                        # the Python workflow (CLI)
config.yaml                      # sources, keywords, report and webhook settings
n8n/daily-digest-workflow.json   # equivalent n8n workflow
tests/                           # offline end-to-end tests + n8n JSON checks
examples/                        # sample digest (Markdown + Excel)
docs/preview.png                 # screenshot of the Excel output
```

## License

MIT
