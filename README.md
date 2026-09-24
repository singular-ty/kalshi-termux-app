# Kalshi Termux Portal

Mobile-first **Kalshi prediction-market** web app for Termux → browser.

- **Public** market scan + exchange status (no keys)
- **Authenticated** balance / positions / orders via RSA-PSS (`KALSHI_KEY_ID` + PEM)
- **Strategy**: high-payout scanner, fractional **Kelly**, **Nash** payoff matrix, optional Monte Carlo sim
- **Safety**: default **DRY-RUN**; live arm requires env flag + typed confirm (+ optional TOTP)
- **Local security**: Fernet vault, `chmod 600` key file, Aegis-style TOTP — no phone-home

> Not financial advice. Prediction markets involve risk of loss. **No 100% win-rate claims.**

## Termux one-shot install

```bash
pkg update -y
pkg install -y python git
# clone your fork / copy this folder onto the phone, then:
cd kalshi-termux-app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# optional: put RSA PEM at secrets/kalshi.key (chmod 600) and set KALSHI_KEY_ID in .env
chmod +x start.sh
./start.sh
```

Then open the printed URL (or run `termux-open-url http://127.0.0.1:8787`).

### Without venv

```bash
pip install --user -r requirements.txt
PYTHONPATH=. python -m uvicorn app.main:app --host 0.0.0.0 --port 8787
```

## Desktop / this machine

```bash
cd /workspace/kalshi-termux-app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./start.sh
```

If port `8787` is busy: `PORT=8788 ./start.sh`.

## Config

| Variable | Meaning |
|----------|---------|
| `KALSHI_HOST` | `external` (default) · `elections` · `demo` · `trading` |
| `KALSHI_KEY_ID` | API key id |
| `KALSHI_KEY_PATH` | PEM path (default `secrets/kalshi.key`) |
| `DRY_RUN` | `1` (default) blocks live arming |
| `KELLY_FRACTION` | fraction of full Kelly (default `0.5`) |
| `KELLY_MAX_FRACTION` | hard cap of bankroll per trade (default `0.05`) |
| `CACHE_TTL_SECONDS` | scanner cache (default `10`) |

API hosts (Trade API v2):

- Recommended: `https://external-api.kalshi.com`
- Also supported: `https://api.elections.kalshi.com`
- Demo: `https://demo-api.kalshi.co`

## API keys (required for Account / live)

A GitHub clone contains no Kalshi credentials. Account data and live trading require a Kalshi **Key ID** plus its private PEM.

1. Log in at [Kalshi](https://kalshi.com/account/profile), open **profile/account → API Keys**, and select **Create New API Key**.
2. Save the Key ID and download the PEM immediately. Kalshi does not let you retrieve the private key later.
3. In **Settings → API credentials**, paste the Key ID and PEM, then choose **Save encrypted**. Alternatively, set `KALSHI_KEY_ID` in your local `.env` and put the PEM at `secrets/kalshi.key` with restrictive permissions.
4. Confirm the Settings badge changes from **No keys** to **Keys on disk** or **Vault unlocked**, then test Account.
5. After the replacement key works, return to the same **API Keys** list and **delete/revoke** the old key.

The **Clear local keys** button only removes the local PEM and runtime/vault Key ID; it does **not** revoke a key at Kalshi. Revoke it separately on Kalshi.com. See [docs/KALSHI_API_KEYS.md](docs/KALSHI_API_KEYS.md) for create, rotate, and delete details. Never commit `.env`, PEM files, or real key material.

## Panels

1. **Markets** — live open-market scan, payout multiples, Nash action, Kelly size  
2. **Contract** — detail + paper/live order gate  
3. **Nash / Kelly** — payoff matrix + Monte Carlo simulation  
4. **Account** — balance / positions / orders (keys required)  
5. **Settings** — host switch, vault, keys, TOTP, arm/disarm live  
6. **Activity** — SQLite activity + order log  

## Auth signing (Kalshi v2)

```
timestamp_ms + METHOD + path_without_query + optional_body
→ RSA-PSS SHA-256 (salt = DIGEST_LENGTH) → base64
Headers: KALSHI-ACCESS-KEY / -SIGNATURE / -TIMESTAMP
```

## License

MIT — see `LICENSE`. Read `DISCLAIMER.md` before trading.
