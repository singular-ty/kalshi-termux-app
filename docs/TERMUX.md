# Termux install

PyPI `cryptography` crashes on Termux (`PyBaseObject_Type` / `_rust.abi3.so`). Install Termux `python-cryptography`, create the venv with `--system-site-packages` so that package is visible, then uninstall the pip overlay that `requirements.txt` installs.

```bash
pkg update -y
pkg install -y python git python-cryptography
git clone https://github.com/singular-ty/kalshi-termux-app.git
cd kalshi-termux-app
python -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
pip uninstall -y cryptography
python -c "from cryptography.hazmat.primitives import hashes; print('ok')"
cp .env.example .env
chmod +x start.sh && ./start.sh
```

The import check should print `ok`. Then open the printed URL (or run `termux-open-url http://127.0.0.1:8787`).

Optional: put the RSA PEM at `secrets/kalshi.key` (`chmod 600`) and set `KALSHI_KEY_ID` in `.env`. See [KALSHI_API_KEYS.md](KALSHI_API_KEYS.md).

## If the import still fails

Preload Termux libpython. The filename matches current Termux `python` (3.13):

```bash
LD_PRELOAD=$PREFIX/lib/libpython3.13.so ./start.sh
```

## Without venv

Install `python-cryptography` from `pkg` and remove any pip-installed `cryptography` so the system module stays in place:

```bash
pkg install -y python-cryptography
pip install --user -r requirements.txt
pip uninstall -y cryptography
PYTHONPATH=. python -m uvicorn app.main:app --host 0.0.0.0 --port 8787
```
