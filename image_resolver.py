"""Resolve preview images and descriptions for entries.

Resolution order (first hit wins):
  Image:  1. enclosure type="image/*"  2. media:content/thumbnail  3. og:image scrape
  Desc:   feed summary > og:description scrape > first <p> tag
"""

from __future__ import annotations

import logging

import requests
from bs4 import BeautifulSoup

from fetcher import Entry, clean_summary, fetch

log = logging.getLogger(__name__)

_OG_ATTRS = ("property", "name")
_OG_IMAGE_VALUES = {"og:image", "twitter:image", "twitter:image:src"}
_OG_DESC_VALUES = {"og:description", "description", "twitter:description"}


def resolve_image(entry: Entry, timeout: int = 12) -> str | None:
    for url in entry.image_urls:
        if url:
            return url

    if not entry.link:
        return None

    try:
        resp = fetch(entry.link, timeout=timeout)
    except requests.RequestException as exc:
        log.warning("failed to scrape image for %s: %s", entry.link, exc)
        return None

    content_type = resp.headers.get("Content-Type", "")
    if "text/html" not in content_type.lower():
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup.find_all("meta"):
        key = tag.get(_OG_ATTRS[0]) or tag.get(_OG_ATTRS[1])
        if key and key.strip().lower() in _OG_IMAGE_VALUES:
            content = (tag.get("content") or "").strip()
            if content:
                return content

    link_tag = soup.find("link", rel="image_src")
    if link_tag and link_tag.get("href"):
        return link_tag["href"]

    return None


def resolve_description(entry: Entry, timeout: int = 12) -> str:
    if entry.summary and len(entry.summary) >= 20:
        return entry.summary

    if not entry.link:
        return ""

    try:
        resp = fetch(entry.link, timeout=timeout)
    except requests.RequestException as exc:
        log.warning("failed to scrape description for %s: %s", entry.link, exc)
        return ""

    content_type = resp.headers.get("Content-Type", "")
    if "text/html" not in content_type.lower():
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup.find_all("meta"):
        key = (tag.get("property") or tag.get("name") or "").strip().lower()
        if key in _OG_DESC_VALUES:
            content = (tag.get("content") or "").strip()
            if content:
                return clean_summary(content)

    p = soup.find("p")
    if p:
        text = p.get_text().strip()
        if text:
            return clean_summary(text)

    return ""
