"""Window definitions and tunable constants."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Window:
    name: str
    lookback_hours: int
    long_read_boost: float
    emoji: str
    label: str


WINDOWS: dict[str, Window] = {
    "morning": Window("morning", 14, 0.0, "🌅", "Morning digest"),
    "midday":  Window("midday",   6, 0.0, "☀️", "Midday digest"),
    "evening": Window("evening",  8, 1.5, "🌙", "Evening digest"),
}

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

MIN_SCORE = 6.0
FALLBACK_MIN_SCORE = 5.0
MAX_STORIES = 6
MIN_STORIES = 4

MAX_CANDIDATES_TO_CLAUDE = 80
