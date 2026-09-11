"""Smoke/regression checks. No framework: python test_icarus.py"""

import os
import random
import sys
import tempfile
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
os.chdir(REPO)

import config as config_mod
import dedup
import fetcher
import filter as filter_mod
import main as main_mod

failures = []


def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}: {name}")
    if not cond:
        failures.append(name)


def matches(text, cats):
    return filter_mod.matches_categories(fetcher.Entry("s", "f", "g", text, "http://x"), cats)


# 1. keyword stems match full words
check("filter matches 'exfiltration'", matches("data exfiltration via malware", ["security"]))
check("filter matches AI 'capability'", matches("OpenAI shows new capability", ["ai"]))
check("filter matches 'fine-tuning'", matches("fine-tuning a model on new data", ["ai"]))
check("filter matches 'pretraining'", matches("pretraining run costs millions", ["ai"]))
check("bare 'capability' is not AI on its own", not matches("the capability of the team", ["ai"]))
check("filter rejects noise", not matches("local bakery opens", ["security", "ai"]))

# 2. config category validation
try:
    config_mod.validate_config({"sites": [{"name": "x", "feed_url": "u"}], "categories": ["nonsense"]})
    check("config rejects bad category", False)
except config_mod.ConfigError:
    check("config rejects bad category", True)

config_mod.validate_config({"sites": [{"name": "x", "feed_url": "u"}],
                            "categories": ["security"], "max_post_per_feed": 2, "max_post_per_run": 3})

# 3. dedup batch query
db = tempfile.mktemp(suffix=".db")
dedup.mark_posted_many([("g1", "f1"), ("g2", "f1"), ("g3", "f2")], db_path=db)
check("posted_guids scoped to feed", dedup.posted_guids("f1", db_path=db) == {"g1", "g2"})

# 4. fetch_feed parses bytes and passes the timeout through
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Feed</title>
<item><title>OpenAI ships GPT-6</title><link>http://a/1</link><guid>a1</guid>
<description>OpenAI announced a new model today with big benchmarks.</description></item>
<item><title>Plain story</title><link>http://a/2</link><guid>a2</guid>
<description>Nothing relevant here about baking bread.</description></item>
</channel></rss>"""

calls = {}


class FakeResp:
    content = RSS


def fake_fetch(url, timeout=15, **kw):
    calls["timeout"] = timeout
    return FakeResp()


fetcher.fetch = fake_fetch
entries = fetcher.fetch_feed("http://feed", timeout=7)
check("fetch_feed passes timeout to requests", calls.get("timeout") == 7)
check("fetch_feed parses entries", {e.guid for e in entries} == {"a1", "a2"})

# 4b. retry/error handling
import requests

import discovery

fetcher.time.sleep = lambda s: None
attempts = {"n": 0}


def flaky_fetch(url, timeout=15, **kw):
    attempts["n"] += 1
    if attempts["n"] == 1:
        raise requests.ConnectionError("boom")
    return FakeResp()


fetcher.fetch = flaky_fetch
entries = fetcher.fetch_feed("http://feed")
check("fetch_feed retries transient HTTP error", attempts["n"] == 2 and len(entries) == 2)


def dead_fetch(url, timeout=15, **kw):
    raise requests.ConnectionError("down")


fetcher.fetch = dead_fetch
try:
    fetcher.fetch_feed("http://feed")
    check("fetch_feed raises when unreachable", False)
except ValueError:
    check("fetch_feed raises when unreachable", True)

discovery.fetch = dead_fetch
check("validate_feed returns False on request error", discovery.validate_feed("http://x") is False)

# 4c. real config + workflow parse
import yaml

try:
    config_mod.validate_config(config_mod.load_config(os.path.join(REPO, "config.yaml")))
    check("real config.yaml validates", True)
except Exception as exc:  # noqa: BLE001
    check(f"real config.yaml validates ({exc})", False)

with open(os.path.join(REPO, ".github/workflows/rss.yml"), encoding="utf-8") as fh:
    wf = yaml.safe_load(fh)
check("workflow yaml parses with a poll job", "poll" in wf.get("jobs", {}))

# 5. end-to-end run_once: budget, fairness, no loss, no reposts
def mk(feed, guid, title):
    return fetcher.Entry("site", feed, guid, title, f"http://x/{guid}",
                         published=datetime.now(timezone.utc))


def make_feed(feed_url):
    if "sec" in feed_url:
        return [mk(feed_url, f"s{i}", f"exploit number {i}") for i in range(5)]
    return [mk(feed_url, f"a{i}", f"OpenAI model {i}") for i in range(5)]


main_mod.fetcher.fetch_feed = lambda url, timeout=15: make_feed(url)
posted = []
main_mod.discord_mod.post_webhook = lambda url, payload, timeout=15: posted.append(payload["embeds"][0]["title"])
main_mod.resolve_image = lambda entry, timeout=12: None
main_mod.resolve_description = lambda entry, timeout=12: ""
main_mod.time.sleep = lambda s: None
dedup.DB_PATH = db

random.seed(0)
os.environ["WEBHOOK_URL"] = "https://example.invalid/webhook"
cfg = {
    "sites": [
        {"name": "sec", "feed_url": "http://sec", "categories": ["security"]},
        {"name": "ai", "feed_url": "http://ai", "categories": ["ai"]},
    ],
    "categories": ["security", "ai"],
    "max_post_per_feed": 5,
    "max_post_per_run": 4,
}

main_mod.run_once(cfg)
check("run1 posts full budget", len(posted) == 4)
check("run1 fair split across feeds",
      sum(t.startswith("exploit") for t in posted) == 2 and sum(t.startswith("OpenAI") for t in posted) == 2)

for _ in range(2):
    main_mod.run_once(cfg)
check("all 10 entries eventually posted, none lost", len(posted) == 10)
posted.clear()
main_mod.run_once(cfg)
check("no reposts once drained", len(posted) == 0)

# 6. per-feed cap marks the excess as seen
db2 = tempfile.mktemp(suffix=".db")
dedup.DB_PATH = db2
site = {"name": "sec", "feed_url": "http://sec", "categories": ["security"], "max": 2}
queue = main_mod._candidates(cfg, site, make_feed("http://sec"))
check("per-feed cap trims queue", len(queue) == 2)
check("excess marked seen", dedup.posted_guids("http://sec", db_path=db2) == {"s2", "s3", "s4"})

for path in (db, db2):
    if os.path.exists(path):
        os.remove(path)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("ALL CHECKS PASSED")
