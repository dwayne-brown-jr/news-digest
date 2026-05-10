# news-digest

Personal news digest delivered to Telegram three times a day. Pulls a curated
RSS list, uses Claude Haiku 4.5 to cluster duplicates across outlets, score
articles 0–10 against a personal interests profile, and write a one-line
"why you'd care" blurb. Top 4–6 stories per run. Runs entirely on GitHub Actions
cron — no server.

## Schedule

| Window  | Local PT | UTC cron     | Lookback | Notes                          |
|---------|----------|--------------|----------|--------------------------------|
| morning | 06:00    | `0 13 * * *` | 14h      |                                |
| midday  | 12:00    | `0 19 * * *` | 6h       |                                |
| evening | 20:00    | `0 3 * * *`  | 8h       | +1.5 boost for long-form sources |

> **DST note**: GH Actions cron is fixed UTC and does not honor DST. The above
> targets PDT (UTC-7). During PST (Nov–Mar) digests fire one hour earlier in
> local time. Edit the cron lines in `.github/workflows/digest.yml` to swap.

## What you can edit without touching code

- **`feeds.yml`** — the RSS list. Add a line `- {name: ..., url: ..., long_form: true}`.
  `long_form: true` triggers the evening boost.
- **`interests.md`** — your interests profile. Embedded verbatim into the
  scoring prompt. Edit and push to retune what gets surfaced.

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
export TELEGRAM_BOT_TOKEN=123456:ABC...
export TELEGRAM_CHAT_ID=123456789

# Dry-run: fetch + filter only, no Claude/Telegram calls
python run.py --window morning --dry-run

# Real run
python run.py --window morning
```

## GitHub Actions secrets

```bash
gh secret set ANTHROPIC_API_KEY
gh secret set TELEGRAM_BOT_TOKEN
gh secret set TELEGRAM_CHAT_ID
```

## Telegram bot setup

1. Message `@BotFather` on Telegram → `/newbot` → follow prompts → save the bot token.
2. Send any message to your new bot from your personal account.
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` and grab the
   `message.chat.id` value — that's your `TELEGRAM_CHAT_ID`.

## Kill switch

Send `/pause 7d` (or `/pause 12h`, `/pause 30m`, `/pause` for the default 1d) to
the bot. The next cron run will pick it up via `getUpdates`, write `state/pause.json`
in the repo, and skip sending until the pause expires. Send `/resume` to clear.

## Project layout

```
.github/workflows/digest.yml   # 3 cron schedules, single job
news_digest/
  config.py    # window definitions + tunable thresholds
  feeds.py     # load feeds.yml, fetch, filter by lookback window
  claude.py    # single Haiku 4.5 call (cluster + score + blurb)
  dedupe.py    # pick highest-scored member per cluster, apply boost
  pause.py     # read/write state/pause.json, parse /pause /resume
  telegram.py  # send_message (HTML), getUpdates polling
  digest.py    # orchestrator
state/pause.json  # persisted across runs via commit-back
feeds.yml         # editable RSS list
interests.md      # editable interests profile (used in scoring prompt)
run.py            # CLI entrypoint
```
