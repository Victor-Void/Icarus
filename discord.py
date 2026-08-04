"""Discord webhook embed formatting and delivery."""

from __future__ import annotations

import logging
import time

import requests

from fetcher import Entry

log = logging.getLogger(__name__)

ACCENT_COLOR = 0x5865F2
POST_DELAY = 2.0


def build_payload(entry: Entry, image_url: str | None, description: str = "") -> dict:
    embed: dict = {"title": entry.title, "color": ACCENT_COLOR}
    if entry.link:
        embed["url"] = entry.link
    if description:
        embed["description"] = description
    elif entry.summary:
        embed["description"] = entry.summary
    if image_url:
        embed["image"] = {"url": image_url}
    embed["footer"] = {"text": entry.site_name}
    if entry.published:
        embed["timestamp"] = entry.published.isoformat()

    return {"embeds": [embed]}


def post_webhook(webhook_url: str, payload: dict, timeout: int = 15) -> None:
    max_retries = 3
    for attempt in range(max_retries):
        resp = requests.post(webhook_url, json=payload, timeout=timeout)
        if resp.status_code == 429:
            try:
                retry_after = resp.json().get("retry_after", POST_DELAY)
            except ValueError:
                retry_after = POST_DELAY
            log.warning("rate limited; waiting %.1fs (attempt %d/%d)", retry_after, attempt + 1, max_retries)
            time.sleep(retry_after)
            continue
        if resp.status_code not in (200, 204):
            raise RuntimeError(f"webhook failed: HTTP {resp.status_code}: {resp.text[:200]}")
        return
    raise RuntimeError(f"webhook still rate-limited after {max_retries} retries")
