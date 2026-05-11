"""Telegram Bot API: send digest message, poll updates for /pause commands."""
from __future__ import annotations

import html
import logging
import os
from dataclasses import dataclass

import requests

from .config import Window
from .dedupe import Pick

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org/bot{token}/{method}"


@dataclass
class TelegramUpdate:
    update_id: int
    text: str
    chat_id: int


def _token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"]


def _chat_id() -> str:
    return os.environ["TELEGRAM_CHAT_ID"]


def get_updates(offset: int) -> list[TelegramUpdate]:
    """Long-poll-free fetch of any messages since `offset`."""
    url = API_BASE.format(token=_token(), method="getUpdates")
    try:
        r = requests.get(url, params={"offset": offset, "timeout": 0}, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("getUpdates failed: %s", e)
        return []

    data = r.json()
    if not data.get("ok"):
        log.warning("getUpdates not ok: %s", data)
        return []

    out: list[TelegramUpdate] = []
    for u in data.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        text = msg.get("text") or ""
        chat = (msg.get("chat") or {}).get("id")
        if chat is None:
            continue
        out.append(TelegramUpdate(update_id=u["update_id"], text=text, chat_id=int(chat)))
    return out


def send_digest(window: Window, picks: list[Pick], now_label: str) -> None:
    body = _format_digest(window, picks, now_label)
    url = API_BASE.format(token=_token(), method="sendMessage")
    r = requests.post(url, json={
        "chat_id": _chat_id(),
        "text": body,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }, timeout=20)
    if r.status_code != 200:
        log.error("sendMessage failed: %s — %s", r.status_code, r.text)
        r.raise_for_status()


HEADLINE_MAX = 100


def _truncate_headline(title: str) -> str:
    if len(title) <= HEADLINE_MAX:
        return title
    cut = title[:HEADLINE_MAX].rsplit(" ", 1)[0].rstrip(",;:—-")
    return cut + "…"


def _format_digest(window: Window, picks: list[Pick], now_label: str) -> str:
    header = f"{window.emoji} <b>{html.escape(window.label)}</b> · {html.escape(now_label)}"
    if not picks:
        return header + "\n\nNo stories cleared the bar this run."

    lines = [header, ""]
    for i, p in enumerate(picks, 1):
        title = html.escape(_truncate_headline(p.article.title))
        source = html.escape(p.article.source)
        blurb = html.escape(p.blurb)
        link = html.escape(p.article.link, quote=True)
        lines.append(f"{i}. <b>{title}</b>")
        lines.append(f"   <i>{source}</i> — {blurb}")
        lines.append(f"   <a href=\"{link}\">Read →</a>")
        lines.append("")
    return "\n".join(lines).rstrip()
