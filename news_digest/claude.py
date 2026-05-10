"""Single Haiku 4.5 call: cluster duplicates + score 0-10 + write blurb.

Prompt is intentionally a v0 — we'll iterate on it.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from anthropic import Anthropic

from .config import CLAUDE_MODEL, MAX_CANDIDATES_TO_CLAUDE
from .feeds import Article

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
INTERESTS_FILE = REPO_ROOT / "interests.md"


@dataclass
class ScoredMember:
    article_id: int
    score: float
    blurb: str


@dataclass
class Cluster:
    topic: str
    members: list[ScoredMember]


SYSTEM_PROMPT_V0 = """You are a ruthless news editor curating a personal digest.

You receive a JSON array of candidate articles (id, title, source, published, summary).
Your job, in one pass:

1. CLUSTER: Group articles that cover the same underlying news event/story across
   outlets. Use a short topic label per cluster. Single-article clusters are fine.

2. SCORE each article 0-10 for how strongly it matches the reader's interests below.
   - 9-10: directly central to a stated interest, high signal, novel
   - 7-8:  clear interest match, worth reading
   - 5-6:  tangential or routine coverage of an interest area
   - 0-4:  off-profile, repetitive, or low-signal

   Be ruthless. Most candidates should land 4-7. Reserve 8+ for genuinely strong matches.

3. BLURB each article in ONE sentence (max ~20 words) starting with a verb or hook,
   explaining what the reader would learn or why it matters TO THEM given their
   interests. No fluff like "this article discusses". No filler.

Reader's interests:
---
{interests}
---

Return ONLY a JSON object — no prose, no markdown fences — matching exactly:

{{
  "clusters": [
    {{
      "topic": "string",
      "members": [
        {{"id": <int>, "score": <number 0-10>, "blurb": "string"}}
      ]
    }}
  ]
}}

Every input article must appear in exactly one cluster's members list."""


def _load_interests() -> str:
    return INTERESTS_FILE.read_text().strip()


def _build_system() -> list[dict]:
    """System block with cache_control so the stable interests+rubric is cached."""
    return [{
        "type": "text",
        "text": SYSTEM_PROMPT_V0.format(interests=_load_interests()),
        "cache_control": {"type": "ephemeral"},
    }]


def _serialize_articles(articles: list[Article]) -> str:
    payload = [
        {
            "id": a.id,
            "title": a.title,
            "source": a.source,
            "published": a.published.isoformat(),
            "summary": a.summary,
        }
        for a in articles
    ]
    return json.dumps(payload, ensure_ascii=False)


def _extract_json(text: str) -> dict:
    """Tolerate stray prose or code fences around the JSON."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object in model output: {text[:200]}")
    return json.loads(text[start:end + 1])


def cluster_score_blurb(articles: list[Article]) -> list[Cluster]:
    if not articles:
        return []
    if len(articles) > MAX_CANDIDATES_TO_CLAUDE:
        log.info("trimming %d → %d candidates", len(articles), MAX_CANDIDATES_TO_CLAUDE)
        articles = articles[:MAX_CANDIDATES_TO_CLAUDE]

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=_build_system(),
        messages=[{"role": "user", "content": _serialize_articles(articles)}],
    )

    text = "".join(block.text for block in resp.content if block.type == "text")
    data = _extract_json(text)

    clusters: list[Cluster] = []
    for c in data.get("clusters", []):
        members = [
            ScoredMember(
                article_id=int(m["id"]),
                score=float(m["score"]),
                blurb=str(m["blurb"]).strip(),
            )
            for m in c.get("members", [])
        ]
        if members:
            clusters.append(Cluster(topic=str(c.get("topic", "")), members=members))

    log.info("Claude returned %d clusters covering %d members",
             len(clusters), sum(len(c.members) for c in clusters))
    return clusters
