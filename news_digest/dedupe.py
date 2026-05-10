"""Pick highest-scored member per cluster, apply window-specific boosts."""
from __future__ import annotations

from dataclasses import dataclass

from .claude import Cluster
from .config import Window
from .feeds import Article


@dataclass
class Pick:
    article: Article
    score: float
    blurb: str
    cluster_topic: str


def select(clusters: list[Cluster], articles: list[Article], window: Window) -> list[Pick]:
    by_id = {a.id: a for a in articles}
    picks: list[Pick] = []

    for cluster in clusters:
        boosted = []
        for m in cluster.members:
            article = by_id.get(m.article_id)
            if article is None:
                continue
            score = m.score
            if window.long_read_boost and article.long_form:
                score += window.long_read_boost
            boosted.append((score, article, m))

        if not boosted:
            continue

        boosted.sort(key=lambda t: (t[0], t[1].long_form), reverse=True)
        best_score, best_article, best_member = boosted[0]
        picks.append(Pick(
            article=best_article,
            score=best_score,
            blurb=best_member.blurb,
            cluster_topic=cluster.topic,
        ))

    return picks
