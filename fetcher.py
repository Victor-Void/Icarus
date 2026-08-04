"""Feed fetching and entry normalization using feedparser."""

from __future__ import annotations

import html as html_mod
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import feedparser
import requests

log = logging.getLogger(__name__)

USER_AGENT = "icarus/1.0 (+https://github.com/Victor-Void/icarus)"


@dataclass
class Entry:
    site_name: str
    feed_url: str
    guid: str
    title: str
    link: str
    summary: str = ""
    published: datetime | None = None
    image_urls: list[str] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _entry_guid(entry: feedparser.FeedParserDict, feed_url: str) -> str:
    for key in ("id", "guid"):
        value = entry.get(key)
        if value:
            return str(value)
    return f"{feed_url}#{entry.get('link', '')}"


def _entry_link(entry: feedparser.FeedParserDict) -> str:
    link = entry.get("link", "")
    if not link and entry.get("links"):
        for l in entry["links"]:
            if l.get("rel") in (None, "alternate", "self") and l.get("href"):
                link = l["href"]
                break
    return str(link)


def _entry_published(entry: feedparser.FeedParserDict) -> datetime | None:
    struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if not struct:
        return None
    try:
        return datetime(*struct[:6], tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _entry_images(entry: feedparser.FeedParserDict) -> list[str]:
    urls: list[str] = []
    for enc in entry.get("enclosures", []) or []:
        if str(enc.get("type", "")).lower().startswith("image/"):
            url = enc.get("href") or enc.get("url")
            if url:
                urls.append(str(url))
    for key in ("media_content", "media_thumbnail", "media:content", "media:thumbnail"):
        for item in entry.get(key, []) or []:
            url = item.get("url")
            if url and str(url) not in urls:
                urls.append(str(url))
    return urls


def truncate(text: str, length: int) -> str:
    text = " ".join(text.split())
    return text[: length - 1] + "\u2026" if len(text) > length else text


_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(value: str) -> str:
    value = _TAG_RE.sub(" ", value)
    return html_mod.unescape(value)


def clean_summary(summary: str) -> str:
    cleaned = truncate(strip_html(summary), 300)
    return cleaned if len(cleaned) >= 20 else ""


def fetch_feed(feed_url: str, timeout: int = 15) -> list[Entry]:
    """Fetch a feed and return normalized entries, newest first."""
    parsed = feedparser.parse(feed_url, agent=USER_AGENT)

    if parsed.get("bozo") and not parsed.entries:
        exc = parsed.get("bozo_exception")
        log.warning("feed parse failed (retrying): %s (%s)", feed_url, exc)
        time.sleep(2)
        parsed = feedparser.parse(feed_url, agent=USER_AGENT)
    if parsed.get("bozo") and not parsed.entries:
        exc = parsed.get("bozo_exception")
        raise ValueError(f"feed not parseable: {feed_url} ({exc})")

    feed_title = parsed.feed.get("title", feed_url)
    entries: list[Entry] = []
    seen: set[str] = set()

    for item in parsed.entries:
        guid = _entry_guid(item, feed_url)
        if guid in seen:
            continue
        seen.add(guid)
        link = _entry_link(item)
        entries.append(
            Entry(
                site_name=feed_title,
                feed_url=feed_url,
                guid=guid,
                title=truncate(strip_html(item.get("title", "").strip()) or "(no title)", 250),
                link=link,
                summary=clean_summary(item.get("summary", "") or item.get("description", "") or ""),
                published=_entry_published(item),
                image_urls=_entry_images(item),
            )
        )

    entries.sort(key=lambda e: e.published or _now(), reverse=True)
    return entries


def fetch(url: str, timeout: int = 15, **kwargs) -> requests.Response:
    """Thin wrapper over requests with a default UA and timeout."""
    kwargs.setdefault("headers", {})["User-Agent"] = USER_AGENT
    kwargs.setdefault("timeout", timeout)
    resp = requests.get(url, **kwargs)
    resp.raise_for_status()
    return resp
