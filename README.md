# news-digest

A personal news digest bot. Pulls a curated RSS list, uses Claude Haiku to cluster duplicate stories and score what's left against a personal interests profile, and delivers a top-stories digest to Telegram three times a day.

**Status:** live

---

## How it works

1. **Fetch** — pull a curated RSS list
2. **Cluster** — Haiku groups the same story reported by five outlets into one item
3. **Score** — each cluster is scored against an interests profile, so relevance is personal rather than generic "top headlines"
4. **Deliver** — the top stories go to Telegram, 3× daily

Runs entirely on GitHub Actions cron. No server to keep alive.

## Why it's built this way

Deduplication is the actual problem with news aggregation — the same story from five sources is five times the noise and none of the signal. Clustering first, then scoring the clusters, is what makes a short digest worth reading.

Using Haiku keeps it cheap enough to run three times a day indefinitely.

## Stack

Python · Anthropic Claude (Haiku) · Telegram Bot API · GitHub Actions cron
