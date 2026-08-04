"""Automatic feed discovery from a bare site URL.

Order of reliability:
  1. <link rel="alternate" type="application/rss+xml|application/atom+xml"> in <head>
  2. common paths (/feed, /rss, /rss.xml, /feed.xml, /atom.xml, /index.xml)
  3. every candidate is validated with feedparser before being trusted
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import feedparser
import requests

from fetcher import USER_AGENT, fetch

log = logging.getLogger(__name__)

FEED_TYPES = {"application/rss+xml", "application/atom+xml"}
GUESS_PATHS = [
    "/feed", "/feed/", "/rss", "/rss/", "/rss.xml",
    "/feed.xml", "/atom.xml", "/index.xml", "/feeds/posts/default",
]
_LINK_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([a-zA-Z_:]+)\s*=\s*["\']([^"\']*)["\']')


def _link_attrs(tag: str) -> dict[str, str]:
    return {k.lower(): v for k, v in _ATTR_RE.findall(tag)}


def _is_comment_feed(url: str) -> bool:
    return "comment" in url.lower()


def validate_feed(url: str, timeout: int = 15) -> bool:
    parsed = feedparser.parse(url, agent=USER_AGENT)
    return not parsed.get("bozo") and bool(parsed.entries)


def discover_feed_urls(site_url: str, timeout: int = 15) -> list[str]:
    """Return validated feed URLs for a site, best match first."""
    site_url = site_url.strip()
    if not urlparse(site_url).scheme:
        site_url = "https://" + site_url

    candidates: list[str] = [site_url]

    try:
        resp = fetch(site_url, timeout=timeout)
    except requests.RequestException as exc:
        raise ValueError(f"could not fetch {site_url}: {exc}") from exc

    content_type = resp.headers.get("Content-Type", "")
    if "text/html" in content_type.lower():
        for tag in _LINK_RE.findall(resp.text):
            attrs = _link_attrs(tag)
            if attrs.get("rel", "").lower() == "alternate" and attrs.get("type") in FEED_TYPES:
                href = attrs.get("href")
                if href:
                    candidates.append(urljoin(site_url, href))

    for path in GUESS_PATHS:
        candidates.append(urljoin(site_url, path))

    validated: list[str] = []
    seen: set[str] = set()
    for url in candidates:
        key = url[:-1] if url.endswith("/") and url != "/" else url
        if key in seen:
            continue
        seen.add(key)
        try:
            if validate_feed(url, timeout=timeout):
                validated.append(url)
                log.debug("validated feed: %s", url)
        except Exception:
            log.debug("feed validation failed for %s", url, exc_info=True)
            continue

    validated.sort(key=lambda u: _is_comment_feed(u))
    return validated
