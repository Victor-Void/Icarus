"""CLI for managing tracked sites.

Usage:
    python manage.py add <url> [--name "My Blog"]
    python manage.py list
    python manage.py remove <index|name>
    python manage.py revalidate
    python manage.py preview <feed-url>
    python manage.py stats
"""

from __future__ import annotations

import argparse
import logging
import sys
from urllib.parse import urlparse

import dedup
import discovery
import fetcher
import filter as filter_mod
from config import load_config, save_config

log = logging.getLogger("icarus")


def _site_name(url: str) -> str:
    host = urlparse(url).netloc
    return host.replace("www.", "") or url


def cmd_add(args: argparse.Namespace, cfg: dict) -> int:
    candidates = discovery.discover_feed_urls(args.site_url)
    if not candidates:
        print(f"No valid feed found for {args.site_url}. Not every site has one.")
        return 1

    feed_url = candidates[0]
    if len(candidates) > 1:
        print("Multiple feeds found:")
        for i, url in enumerate(candidates):
            print(f"  [{i}] {url}")
        if sys.stdin.isatty():
            choice = input("Pick one (default 0): ").strip()
        else:
            choice = ""
        if choice.isdigit() and int(choice) < len(candidates):
            feed_url = candidates[int(choice)]

    name = args.name or _site_name(args.site_url)
    for site in cfg.get("sites", []):
        if site["feed_url"] == feed_url:
            print(f"Already tracked: {site.get('name', feed_url)} ({feed_url})")
            return 0

    cfg.setdefault("sites", []).append({"name": name, "feed_url": feed_url})
    save_config(cfg)
    print(f"Added {name} -> {feed_url}")
    return 0


def cmd_list(args: argparse.Namespace, cfg: dict) -> int:
    sites = cfg.get("sites", [])
    if not sites:
        print("No sites tracked yet. Use: python manage.py add <url>")
        return 0
    for i, site in enumerate(sites):
        cats = site.get("categories", cfg.get("categories", []))
        cat_str = f" [{','.join(cats)}]" if cats else ""
        print(f"[{i}] {site.get('name')}  ->  {site['feed_url']}{cat_str}")
    return 0


def cmd_remove(args: argparse.Namespace, cfg: dict) -> int:
    sites = cfg.get("sites", [])
    if args.target.isdigit():
        idx = int(args.target)
        if idx >= len(sites):
            print(f"Index {idx} out of range")
            return 1
        removed = sites.pop(idx)
    else:
        for i, site in enumerate(sites):
            if site.get("name", "").lower() == args.target.lower():
                removed = sites.pop(i)
                break
        else:
            print(f"No site named '{args.target}'")
            return 1
    cfg["sites"] = sites
    save_config(cfg)
    print(f"Removed {removed.get('name')} ({removed['feed_url']})")
    return 0


def cmd_revalidate(args: argparse.Namespace, cfg: dict) -> int:
    sites = cfg.get("sites", [])
    if not sites:
        print("No sites tracked yet.")
        return 0
    dead = 0
    for site in sites:
        name = site.get("name", site["feed_url"])
        print(f"Checking {name} ...", end=" ", flush=True)
        if discovery.validate_feed(site["feed_url"]):
            print("ok")
        else:
            print("DEAD")
            dead += 1
    print(f"\n{dead} dead feed(s) found." if dead else "\nAll feeds healthy.")
    return 0


def cmd_preview(args: argparse.Namespace, cfg: dict) -> int:
    feed_url = args.feed_url
    categories = cfg.get("categories", [])

    try:
        entries = fetcher.fetch_feed(feed_url)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to fetch {feed_url}: {exc}")
        return 1

    per_feed = cfg.get("max_post_per_feed", 4)

    if not categories:
        matching = entries
        label = "all (no filter configured)"
    else:
        matching = [e for e in entries if filter_mod.matches_categories(e, categories)]
        label = f"matching {categories}"

    print(f"Feed:  {feed_url}")
    print(f"Fetched: {len(entries)} entries  |  {label}: {len(matching)}")
    print(f"Would post up to {min(len(matching), per_feed)} (cap: {per_feed})")
    print()

    for i, e in enumerate(matching):
        if args.limit and i >= args.limit:
            remainder = len(matching) - i
            if remainder > 0:
                print(f"  ... and {remainder} more (use --limit N to show more)")
            break

        categories_str = ""
        if args.verbose and categories:
            reasons = filter_mod.matching_keywords(e, categories)
            detail = ", ".join(f"{c}:{','.join(r)}" for c, r in reasons.items())
            categories_str = f"  [{detail}]"
        print(f"  [{e.published or '?'}] {e.title}{categories_str}")

    if not matching:
        print("  (none)")

    return 0


def cmd_stats(args: argparse.Namespace, cfg: dict) -> int:
    sites = cfg.get("sites", [])
    total = dedup.count()
    oldest = dedup.oldest_date()

    print(f"State DB: {total} entries")
    if oldest:
        print(f"Oldest entry: {oldest[:10]}")
    print(f"Budget: {cfg.get('max_post_per_run', 10)} per run  |  per-feed cap: {cfg.get('max_post_per_feed', 4)}")
    print(f"Categories: {cfg.get('categories', [])}")
    print()

    if not sites:
        print("No sites tracked.")
        return 0

    for site in sites:
        name = site.get("name", site["feed_url"])
        cats = site.get("categories", cfg.get("categories", []))
        cat_str = f" [{','.join(cats)}]" if cats else ""
        per_feed = site.get("max", cfg.get("max_post_per_feed", 4))
        posted = dedup.count_for_feed(site["feed_url"])
        print(f"  {name}{cat_str}  |  posted: {posted}  (cap: {per_feed})")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config.yaml", help="path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="discover and add a site")
    p_add.add_argument("site_url")
    p_add.add_argument("--name", default=None)
    p_add.set_defaults(fn=cmd_add)

    p_list = sub.add_parser("list", help="list tracked sites")
    p_list.set_defaults(fn=cmd_list)

    p_rm = sub.add_parser("remove", help="remove a site by index or name")
    p_rm.add_argument("target")
    p_rm.set_defaults(fn=cmd_remove)

    p_re = sub.add_parser("revalidate", help="check stored feeds for dead ones")
    p_re.set_defaults(fn=cmd_revalidate)

    p_pv = sub.add_parser("preview", help="test a feed URL with the configured filter")
    p_pv.add_argument("feed_url")
    p_pv.add_argument("-v", "--verbose", action="store_true", help="show matched keywords")
    p_pv.add_argument("--limit", type=int, metavar="N", help="show at most N entries")
    p_pv.set_defaults(fn=cmd_preview)

    p_st = sub.add_parser("stats", help="show database and per-feed statistics")
    p_st.set_defaults(fn=cmd_stats)

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    cfg = load_config(args.config)
    return args.fn(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
