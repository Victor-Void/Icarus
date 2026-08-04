"""config.yaml loading and helpers."""

from __future__ import annotations

import os
from typing import Any

import yaml

CONFIG_PATH = "config.yaml"


class ConfigError(RuntimeError):
    pass


def load_config(path: str = CONFIG_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return cfg


def webhook_url(cfg: dict[str, Any]) -> str:
    url = os.environ.get("WEBHOOK_URL", "").strip() or str(cfg.get("webhook_url") or "").strip()
    if not url:
        raise ConfigError("webhook_url is not set in config.yaml or WEBHOOK_URL env var")
    return url


def save_config(cfg: dict[str, Any], path: str = CONFIG_PATH) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, sort_keys=False, allow_unicode=True)


def validate_config(cfg: dict[str, Any]) -> None:
    if not cfg.get("sites"):
        raise ConfigError("no sites configured in config.yaml — use 'manage.py add <url>'")
    for site in cfg["sites"]:
        if not site.get("feed_url"):
            raise ConfigError(f"site '{site.get('name', '?')}' is missing feed_url")
    mppf = cfg.get("max_post_per_feed", 0)
    if not isinstance(mppf, int) or mppf < 1:
        raise ConfigError("max_post_per_feed must be >= 1")
    mppr = cfg.get("max_post_per_run", 0)
    if not isinstance(mppr, int) or mppr < 1:
        raise ConfigError("max_post_per_run must be >= 1")
