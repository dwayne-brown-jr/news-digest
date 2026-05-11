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


SYSTEM_PROMPT_V1 = """You are a ruthless personal news editor. You curate a tight digest of 4-6
stories per day for ONE specific reader. Be decisive, be skeptical, be brief.

You receive a JSON array of candidate articles (id, title, source, published, summary).
Do all three jobs in a single pass:

═══════════════════════════════════════════════
1) CLUSTER aggressively
═══════════════════════════════════════════════
Group every article that covers the SAME underlying news event into one cluster.
"Same event" = same trigger, same week, same primary subject — even when outlets
frame it differently or add a different angle.

Examples of correct clustering:
  ✓ "Oil jumps on Iran tensions" + "China inflation tops estimates as Iran war
     drives energy" → SAME cluster (both anchored to Iran-driven energy spike)
  ✓ "OpenAI ships new model" + "Sam Altman: GPT-X is here" → SAME cluster
  ✓ "Fed signals rate cut" + "Tech stocks rally on Fed news" → SAME cluster,
     not two

DISTINCT SIGNAL RULE: Cluster only when articles are restatements of the same
underlying event/announcement. If an article carries a NEW data point, a NEW
analytical angle, or a NEW stakeholder's substantive response — keep it
separate, even if it traces back to the same root cause:

  ✗ "Trump rejects Iran peace counteroffer" + "China inflation tops estimates
     as Iran war drives energy costs" → SEPARATE. The first is the geopolitical
     trigger; the second carries a distinct macro data point (China CPI print)
     that the first doesn't. The reader gains from both.
  ✗ "Nvidia AI capex hits $40B" + "Big Tech AI spending starves buybacks" →
     SEPARATE. First is a vendor-side capex story; second is a Goldman analysis
     on shareholder-return dynamics. Different mechanism, different audience.
  ✓ "Trump rejects Iran offer" + "Iran says it will 'never bow' to Trump" →
     SAME cluster. Both reporting the same diplomatic exchange, no new data.
  ✓ "Reuters: Cerebras IPO range raised" + "WSJ: Cerebras ups IPO target on
     demand" → SAME cluster. Same announcement, different outlets.

The bar for clustering is high: pure duplicates and reactionary rewrites only.
When in doubt, keep them separate — distinct angles are more valuable than
slot conservation.

═══════════════════════════════════════════════
2) SCORE 0-10 for THIS reader
═══════════════════════════════════════════════
Reader's interests:
---
{interests}
---

Rubric:
  9-10: Bullseye — direct interest match AND novel/non-obvious AND substantive.
        Reserve for the top ~5% of articles. A new frontier-AI capability
        announcement, a genuinely new piece of medical research, a sharp
        analytical essay on policy.
  7-8:  Clear interest match, worth the reader's time, has real signal.
        A meaningful product launch in their domain, a notable market move
        with explanation, a strong investigative piece.
  5-6:  Tangential or routine coverage of an interest area.
        Daily market chatter, generic political horse-race coverage, recap
        of yesterday's news, vendor PR pieces.
  0-4:  Off-profile, low-signal, or recycled wire copy.
        Celebrity gossip, sports unrelated to fitness/longevity, regional
        news without broader implication.

Anti-patterns to PENALIZE (cap at 6 even if topic matches):
  - "Stocks moved on X" with no analysis of why it matters going forward
  - Politician-said-thing reactions with no policy substance
  - Press-release rewrites and earnings-day recaps
  - Lifestyle pieces masquerading as health/science
  - Anything where the headline is the whole story
  - Vendor- or consultant-driven "study/report finds" pieces where the source is
    a firm with a commercial stake in the conclusion (cap at 5). Example:
    "IBM study finds most companies now have a chief AI officer" — IBM sells
    AI consulting, so the survey is marketing dressed as journalism.
    EXCEPTION: peer-reviewed academic studies, government data releases, or
    research from independent labs are NOT vendor PR — score on merit.

Be ruthless. Most candidates should land 4-7. 8+ should feel earned.

═══════════════════════════════════════════════
3) BLURB in one sentence (≤22 words)
═══════════════════════════════════════════════
The blurb is NOT a summary. It is the reader's reason to click — what they
will gain that they don't already know.

Style:
  ✓ Lead with the insight, the stake, or the surprising detail.
  ✓ Make the connection to the reader's interests explicit when non-obvious.
  ✓ Concrete > abstract. Names, numbers, mechanisms.

Anti-patterns:
  ✗ "This article discusses..." / "The piece explores..." / "A new report on..."
  ✗ Restating the headline in different words.
  ✗ Vague gestures: "important implications", "could change everything".

Examples of GOOD blurbs:
  "Anthropic's new agent benchmark shows Sonnet beating o4 on multi-step coding —
   first credible challenge to OpenAI's reasoning lead this quarter."
  "Why a 0.25% Fed cut matters more than usual: it unlocks $400B in pent-up
   refinancing that's been waiting since March."

Examples of BAD blurbs:
  "The Fed announced a rate cut today, with implications for markets."  ← summary
  "This is an interesting read on AI safety."                            ← vague
  "Anthropic released Claude 4.7 today."                                 ← headline restated

═══════════════════════════════════════════════
Output format
═══════════════════════════════════════════════
Return ONLY a JSON object — no prose, no markdown fences — matching exactly:

{{
  "clusters": [
    {{
      "topic": "short label (3-5 words)",
      "members": [
        {{"id": <int>, "score": <number 0-10>, "blurb": "string"}}
      ]
    }}
  ]
}}

Every input article must appear in exactly one cluster's members list. No commentary."""


def _load_interests() -> str:
    return INTERESTS_FILE.read_text().strip()


def _build_system() -> list[dict]:
    """System block with cache_control so the stable interests+rubric is cached."""
    return [{
        "type": "text",
        "text": SYSTEM_PROMPT_V1.format(interests=_load_interests()),
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
