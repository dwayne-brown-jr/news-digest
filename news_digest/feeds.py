"""Load feed list, fetch via feedparser, filter by lookback window."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

import feedparser
import yaml
from dateutil import parser as dateparser

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
FEEDS_FILE = REPO_ROOT / "feeds.yml"

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Article:
    id: int
    title: str
    source: str
    link: str
    published: datetime
    summary: str
    long_form: bool


@dataclass
class Feed:
    name: str
    url: str
    long_form: bool = False


def load_feeds(path: Path = FEEDS_FILE) -> list[Feed]:
    raw = yaml.safe_load(path.read_text())
    return [Feed(name=r["name"], url=r["url"], long_form=bool(r.get("long_form", False))) for r in raw]


def _strip_html(text: str) -> str:
    return unescape(_TAG_RE.sub("", text or "")).strip()


def _entry_published(entry) -> datetime | None:
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            try:
                dt = dateparser.parse(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (ValueError, TypeError):
                continue
    return None


def fetch_window(lookback_hours: int, feeds: list[Feed] | None = None) -> list[Article]:
    """Fetch all feeds, return articles published within the lookback window."""
    feeds = feeds or load_feeds()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    out: list[Article] = []
    next_id = 0

    for feed in feeds:
        try:
            parsed = feedparser.parse(feed.url)
        except Exception as e:
            log.warning("feed fetch failed: %s — %s", feed.name, e)
            continue
        if parsed.bozo and not parsed.entries:
            log.warning("feed unparseable: %s — %s", feed.name, parsed.bozo_exception)
            continue

        for entry in parsed.entries:
            pub = _entry_published(entry)
            if pub is None or pub < cutoff:
                continue
            title = _strip_html(entry.get("title", "")).strip()
            link = entry.get("link", "")
            if not title or not link:
                continue
            suffix = f" - {feed.name}"
            if title.endswith(suffix):
                title = title[:-len(suffix)].rstrip()
            summary = _strip_html(entry.get("summary") or entry.get("description") or "")
            if len(summary) > 600:
                summary = summary[:600].rsplit(" ", 1)[0] + "…"
            out.append(Article(
                id=next_id,
                title=title,
                source=feed.name,
                link=link,
                published=pub,
                summary=summary,
                long_form=feed.long_form,
            ))
            next_id += 1

    out.sort(key=lambda a: a.published, reverse=True)
    return out
