# TEST_REPORT — Kalshi Termux Portal

**When:** 2026-09-24 ~15:08 MT (America/Denver)  
**Target:** `/workspace/kalshi-termux-app` @ `http://127.0.0.1:8787`  
**Host under test:** `https://external-api.kalshi.com` (also verified `api.elections.kalshi.com`)  
**GitHub push:** not done (per instructions)

## Summary

| | |
|--|--|
| **Overall** | **PASS** (core product + live public/auth paths) |
| Automated checks | 32/32 after correcting key-presence assumptions |
| First-scan bug | Found & fixed mid-test (`mve_filter=exclude`) |
| DRY-RUN default | **PASS** |
| Live Kalshi data | **PASS** |
| Secrets committed | **No** (`.env`, `*.key`, `data/` gitignored) |

## Pass / fail table

| # | Check | Result | Notes |
|---|--------|--------|-------|
| 1 | `python` import `app.main` | **PASS** | title `Kalshi Termux Portal` |
| 2 | `./start.sh` boots uvicorn `0.0.0.0:8787` | **PASS** | prints `termux-open-url` tip |
| 3 | `GET /api/health` | **PASS** | |
| 4 | Live `GET /exchange/status` via `/api/ping` | **PASS** | `exchange_active=true` |
| 5 | Host switch → elections + ping | **PASS** | both hosts live |
| 6 | Live markets scan (enriched > 0) | **PASS** | after MVE fix: 50–100 enriched |
| 7 | Scan timestamps + API host shown | **PASS** | |
| 8 | Honesty disclaimer (no 100% win claim) | **PASS** | |
| 9 | High-payout singles (≥2x) | **PASS** | limit=100 → 40× ≥2x, 12× ≥5x, 11× ≥10x (incl. 1¢ tails) |
| 10 | Nash action on scan rows | **PASS** | BUY_YES / BUY_NO / PASS |
| 11 | Kelly sizing on scan rows | **PASS** | fractional + hard max 5% bankroll |
| 12 | Contract detail + orderbook attempt | **PASS** | |
| 13 | Nash payoff matrix API | **PASS** | BUY_YES / BUY_NO / PASS EVs |
| 14 | Kelly criterion API | **PASS** | |
| 15 | Monte Carlo labeled as simulation | **PASS** | “not quantum magic” |
| 16 | DRY_RUN env default | **PASS** | `DRY_RUN=1` |
| 17 | Effective mode DRY_RUN on boot | **PASS** | `live_armed=false` |
| 18 | Paper order logged, not sent | **PASS** | `[DRY-RUN] Would BUY…` in SQLite |
| 19 | Arm LIVE blocked while DRY_RUN=1 | **PASS** | clear error message |
| 20 | RSA-PSS signer + KALSHI-ACCESS-* headers | **PASS** | code path present |
| 21 | Auth balance (local keys present) | **PASS** | ~$50.01 returned; key material not logged |
| 22 | Auth positions | **PASS** | |
| 23 | Token-bucket + cache TTL ≤15s | **PASS** | TTL=10s |
| 24 | WS URL configured (optional) | **PASS** | not wired into UI (see gaps) |
| 25 | Termux README one-shot | **PASS** | `pkg install python`, venv, `./start.sh` |
| 26 | UI lexicon Kalshi-only | **PASS** | no Ghostlight/Heimdall/glyph/Hz strings |
| 27 | SQLite activity + order log | **PASS** | |
| 28 | `.gitignore` covers `.env` / `*.key` / `data/` | **PASS** | |

### Mid-test failure → fix

| Check | Initial | After fix |
|-------|---------|-----------|
| Markets scan enriched count | **FAIL** (0/15) — open book flooded with `CROSSCATEGORY` MVE at 0¢ | **PASS** — default `mve_filter=exclude` + skip zero asks + light pagination |

## Feature parity vs Gemini thread

| Gemini / engine capability | Portal status |
|----------------------------|---------------|
| RSA-PSS Kalshi client | **Yes** (`app/kalshi/client.py`) |
| Public exchange ping | **Yes** |
| Open markets scan / cheap YES-NO | **Yes** (high-payout board; MVE excluded) |
| Token-bucket rate limit | **Yes** (REST) |
| Fractional Kelly + hard max | **Yes** |
| Nash / Socratic payoff matrix | **Yes** (deterministic; no LLM) |
| Double-slit Monte Carlo | **Yes** (honestly labeled simulation) |
| WebSocket orderbook stream | **Partial** — URL in config; UI uses aggressive REST poll + 10s SQLite TTL (Termux-friendly) |
| Live order POST | **Gated** — dry-run default; arm + typed confirm; no auto-fire on startup |
| Command-center menu | Replaced by **mobile SPA panels** |
| Hz / Heimdall / Glyphstream UI copy | **Removed** (math kept, branding out) |

## How to run (verified)

```bash
cd /workspace/kalshi-termux-app
source .venv/bin/activate   # or create via README
./start.sh                  # http://127.0.0.1:8787
# Termux: termux-open-url http://127.0.0.1:8787
```

If port busy: `PORT=8788 ./start.sh`.

## API host quirks

1. **Recommended host:** `https://external-api.kalshi.com` — works.
2. **Also supported:** `https://api.elections.kalshi.com` — works for status + markets + auth.
3. **`status=open` without `mve_filter=exclude`:** first pages are mostly multivariate `CROSSCATEGORY` combos with `yes_ask_dollars=0` → useless for single-contract scanner.
4. **Prices:** prefer `*_ask_dollars` strings (e.g. `"0.22"`); cents integer fields are legacy fallback.
5. **Balance:** API returns cents integer *and* `balance_dollars` string; portal exposes dollars.
6. **Rate limits:** burst scanning can 429; token bucket + short sleeps help.

## Secrets / safety notes

- A local `.env` + `secrets/kalshi.key` were present on the box during testing (mode `600`). They are **gitignored**. This report does **not** reproduce key ids or PEM.
- Authenticated calls succeeded against live Kalshi (balance ≈ $50).  
- **DRY_RUN remained on**; no live order was placed. Arming requires `DRY_RUN=0` + typed `ARM LIVE` (+ TOTP if configured) + per-order `PLACE LIVE ORDER`.

## Remaining gaps

1. **WebSocket listener not in UI** — REST polling only; WS constants ready for a future toggle.
2. **Model P(YES)** defaults to conservative shrink-toward-0.5 when user does not supply a probability — no LLM assist (by design).
3. **Demo host** (`demo-api.kalshi.co`) not smoke-tested.
4. **Extreme 1¢ / 100x rows** appear in high-payout sort — mathematically correct payout multiples, but Nash/Kelly correctly stress thin edge / tail risk; UI could add an explicit “exclude sub-2¢ junk tails” filter later.
5. **Coordinator** still owns GitHub publish — do not commit `.env` / keys.
6. Optional: wire Aegis QR rendering (currently otpauth URI text only).

## Sample live scan (anonymized)

After fix, `limit=100` on external host returned high-payout singles such as silver threshold contracts at ~1¢ YES (~100x face) and many ≥2x–13x+ style asks across sports/macro. Nash actions and Kelly contract counts populated on each row; timestamps and host echoed in API + UI meta line.

---
*Generated by executor smoke suite against live Kalshi APIs. Not financial advice.*
