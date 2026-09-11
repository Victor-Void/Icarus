"""One-shot run: fetch feeds -> dedup -> resolve images -> post to Discord.

Usage:
    python main.py               # single run (GitHub Actions, cron, systemd)
    python main.py --loop 30     # poll every 30 minutes (Docker/homelab)
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import config as config_mod
import dedup
import discord as discord_mod
import fetcher
import filter as filter_mod
from config import load_config, validate_config, webhook_url
from image_resolver import resolve_description, resolve_image

log = logging.getLogger("icarus")


def _parallel_fetch(sites: list[dict], max_workers: int = 5) -> dict[str, list[fetcher.Entry] | None]:
    """Fetch all feeds in parallel.  Returns {feed_url: entries | None (on error)}."""
    results: dict[str, list[fetcher.Entry] | None] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetcher.fetch_feed, s["feed_url"]): s for s in sites}
        for future in as_completed(futures):
            site = futures[future]
            feed_url = site["feed_url"]
            try:
                results[feed_url] = future.result()
            except Exception as exc:  # noqa: BLE001
                log.error("failed to fetch %s: %s", feed_url, exc)
                results[feed_url] = None
    return results


def _candidates(cfg: dict, site: dict, entries: list[fetcher.Entry]) -> list[fetcher.Entry]:
    """New, filter-matching entries for a feed (one dedup query + one mark batch)."""
    seen = dedup.posted_guids(site["feed_url"])
    new_entries = [e for e in entries if e.guid not in seen]
    categories = site.get("categories") or cfg.get("categories") or []
    if categories:
        keep = [e for e in new_entries if filter_mod.matches_categories(e, categories)]
    else:
        keep = new_entries

    cap = int(site.get("max") or cfg.get("max_post_per_feed", 5))
    to_post = keep[:cap]
    to_post_guids = {e.guid for e in to_post}
    # Everything else (rejected by the filter, or past the per-feed cap) is seen forever.
    dedup.mark_posted_many([(e.guid, e.feed_url) for e in new_entries if e.guid not in to_post_guids])
    return to_post


def _post(cfg: dict, site: dict, webhook: str, entry: fetcher.Entry) -> bool:
    image_url = None
    if cfg.get("resolve_images", True):
        try:
            image_url = resolve_image(entry)
        except Exception as exc:  # noqa: BLE001
            log.warning("image resolution failed for %s: %s", entry.link, exc)

    description = entry.summary
    if not description and cfg.get("resolve_descriptions", True):
        try:
            description = resolve_description(entry)
        except Exception as exc:  # noqa: BLE001
            log.warning("description resolution failed for %s: %s", entry.link, exc)

    payload = discord_mod.build_payload(entry, image_url, description)
    try:
        discord_mod.post_webhook(webhook, payload)
    except RuntimeError as exc:
        log.error("webhook post failed for %s: %s", entry.link, exc)
        return False

    dedup.mark_posted(entry.guid, entry.feed_url)
    log.info("posted [%s] %s", site.get("name", entry.site_name), entry.title)
    time.sleep(discord_mod.POST_DELAY)
    return True


def run_once(cfg: dict) -> None:
    validate_config(cfg)
    webhook = webhook_url(cfg)
    budget = int(cfg.get("max_post_per_run", 10))
    sites = cfg.get("sites", [])

    feed_results = _parallel_fetch(sites)

    queues: list[list] = []
    for site in sites:
        name = site.get("name", site.get("feed_url"))
        entries = feed_results.get(site["feed_url"])
        if entries is None:
            log.info("%s: fetch failed", name)
            continue
        queue = _candidates(cfg, site, entries)
        log.info("%s: %d to post", name, len(queue))
        if queue:
            queues.append([site, queue])

    # Shuffle so the global budget can't always be eaten by the first feeds.
    random.shuffle(queues)

    total_posted = 0
    while budget > 0 and any(queue for _, queue in queues):
        for item in queues:
            if budget <= 0:
                break
            site, queue = item
            if not queue:
                continue
            if _post(cfg, site, webhook, queue.pop(0)):
                budget -= 1
                total_posted += 1

    log.info("run complete: %d posted", total_posted)
    dedup.prune()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", type=float, metavar="MINUTES", default=0,
                        help="poll every N minutes instead of running once")
    parser.add_argument("--config", default=config_mod.CONFIG_PATH, help="path to config.yaml")
    parser.add_argument("--db", default=dedup.DB_PATH, help="path to state.db")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    fetcher.log.setLevel(logging.WARNING)

    dedup.DB_PATH = args.db

    cfg = load_config(args.config)
    if args.loop > 0:
        while True:
            try:
                run_once(cfg)
            except Exception:
                log.exception("run failed")
            log.info("sleeping %.0f minutes", args.loop)
            time.sleep(args.loop * 60)
        return 0
    run_once(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
