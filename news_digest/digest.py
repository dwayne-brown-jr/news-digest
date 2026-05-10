"""Orchestrator: pause check → fetch → Claude → dedupe → Telegram send."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import claude, dedupe, feeds, pause, telegram
from .config import (
    FALLBACK_MIN_SCORE,
    MAX_STORIES,
    MIN_SCORE,
    MIN_STORIES,
    WINDOWS,
    Window,
)

log = logging.getLogger(__name__)


def _select_top(picks, threshold: float) -> list:
    survivors = [p for p in picks if p.score >= threshold]
    survivors.sort(key=lambda p: p.score, reverse=True)
    return survivors[:MAX_STORIES]


def _now_label(window: Window) -> str:
    pt = datetime.now(ZoneInfo("America/Los_Angeles"))
    return pt.strftime("%a %b %-d · %-I%p PT").lower().replace("am", "am").replace("pm", "pm")


def run(window_name: str, *, dry_run: bool = False) -> int:
    window = WINDOWS[window_name]
    log.info("=== %s window — lookback %dh ===", window.name, window.lookback_hours)

    state = pause.load()

    if not dry_run:
        updates = telegram.get_updates(offset=state.last_update_id + 1)
        if updates:
            log.info("processing %d telegram update(s)", len(updates))
        for u in updates:
            state = pause.apply_command(state, u.text)
            state = pause.PauseState(paused_until=state.paused_until, last_update_id=u.update_id)
        if updates:
            pause.save(state)

    if state.is_paused():
        log.info("paused until %s — exiting", state.paused_until)
        return 0

    articles = feeds.fetch_window(window.lookback_hours)
    log.info("fetched %d articles in window", len(articles))

    if dry_run:
        for a in articles[:30]:
            print(f"  [{a.source}] {a.title}  ({a.published.isoformat()})")
        print(f"... {len(articles)} total")
        return 0

    if not articles:
        log.info("no articles in window — skipping send")
        return 0

    clusters = claude.cluster_score_blurb(articles)
    picks = dedupe.select(clusters, articles, window)

    top = _select_top(picks, MIN_SCORE)
    if len(top) < MIN_STORIES:
        log.info("only %d ≥ %.1f — relaxing to %.1f", len(top), MIN_SCORE, FALLBACK_MIN_SCORE)
        top = _select_top(picks, FALLBACK_MIN_SCORE)

    if len(top) < 2:
        log.info("still only %d picks — skipping send", len(top))
        return 0

    log.info("sending %d picks", len(top))
    telegram.send_digest(window, top, _now_label(window))
    return 0
