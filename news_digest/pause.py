"""Read/write pause state. Parse /pause and /resume commands."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = REPO_ROOT / "state" / "pause.json"

_DURATION_RE = re.compile(r"^(\d+)\s*([dhm])$", re.IGNORECASE)


@dataclass
class PauseState:
    paused_until: datetime | None
    last_update_id: int

    def to_json(self) -> dict:
        return {
            "paused_until": self.paused_until.isoformat() if self.paused_until else None,
            "last_update_id": self.last_update_id,
        }

    def is_paused(self, now: datetime | None = None) -> bool:
        if self.paused_until is None:
            return False
        return self.paused_until > (now or datetime.now(timezone.utc))


def load() -> PauseState:
    if not STATE_FILE.exists():
        return PauseState(paused_until=None, last_update_id=0)
    raw = json.loads(STATE_FILE.read_text())
    pu = raw.get("paused_until")
    return PauseState(
        paused_until=datetime.fromisoformat(pu) if pu else None,
        last_update_id=int(raw.get("last_update_id", 0)),
    )


def save(state: PauseState) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state.to_json(), indent=2) + "\n")


def parse_duration(s: str) -> timedelta | None:
    m = _DURATION_RE.match(s.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit == "d":
        return timedelta(days=n)
    if unit == "h":
        return timedelta(hours=n)
    if unit == "m":
        return timedelta(minutes=n)
    return None


def apply_command(state: PauseState, text: str, now: datetime | None = None) -> PauseState:
    """Mutate state for /pause Nd, /pause Nh, /pause Nm, or /resume. No-op otherwise."""
    text = text.strip()
    now = now or datetime.now(timezone.utc)

    if text.lower().startswith("/resume"):
        log.info("/resume → clearing pause")
        return PauseState(paused_until=None, last_update_id=state.last_update_id)

    if text.lower().startswith("/pause"):
        rest = text[len("/pause"):].strip()
        delta = parse_duration(rest) if rest else timedelta(days=1)
        if delta is None:
            log.warning("/pause with bad duration %r — ignoring", rest)
            return state
        until = now + delta
        log.info("/pause %s → paused until %s", rest or "(default 1d)", until.isoformat())
        return PauseState(paused_until=until, last_update_id=state.last_update_id)

    return state
