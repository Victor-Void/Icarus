# Icarus

A small RSS-to-Discord news bot. Icarus watches a set of RSS feeds, picks out the posts that matter to you, and posts them to a Discord channel as embeds.

No AI, no APIs to pay for — just plain Python, keyword filtering, and a webhook.

## What it does

- Polls 13 feeds across security and AI news (Hacker News, Ars Technica, The Verge, The Hacker News, BleepingComputer, Krebs, Exploit-DB, CISA, The Decoder, VentureBeat, TechCrunch, MIT Tech Review, ...)
- Filters posts to the topics you care about with keyword matching (security, CVEs, exploits, AI model releases, pricing, benchmarks, ...)
- Dedupes against a local SQLite database so you never see the same post twice
- Resolves a thumbnail image and description for each post
- Posts a clean embed per article, with rate-limit awareness
- Caps posts per feed and per run to avoid flooding the channel

## Setup

```bash
pip install -r requirements.txt
```

Create a Discord webhook and put it in `config.yaml` (or set the `WEBHOOK_URL` env var):

```yaml
webhook_url: https://discord.com/api/webhooks/...
```

Edit `config.yaml` to add/remove feeds and tweak limits.

## Run

One-shot poll:

```bash
python main.py
```

Keep running (poll every 30 min):

```bash
python main.py --loop 30
```

Or with Docker:

```bash
docker compose up --build
```

## Managing feeds

```bash
python manage.py list                    # show tracked feeds
python manage.py add <url>               # discover and add a feed
python manage.py remove <index|name>     # drop a feed
python manage.py preview <url>           # test a feed against the filter
python manage.py stats                   # db + per-feed stats
python manage.py revalidate              # check for dead feeds
```
