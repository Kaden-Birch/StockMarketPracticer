# AIPTP Deployment Guide

## Desktop Mode (single user)

Run locally with auth disabled, bound to 127.0.0.1:

```bash
pip install ./backend
cd frontend && npm install && npm run build && cd ..
aiptp                       # http://127.0.0.1:8420
```

Native installers (Tauri shell in `desktop/`) are built by the
`Desktop` GitHub Actions workflow on version tags — see `desktop/README.md`.

## Server Mode (24/7)

```bash
./deploy/aiptp.sh up        # builds and starts; open http://<host>:8420
./deploy/aiptp.sh status    # container + health state
./deploy/aiptp.sh logs
./deploy/aiptp.sh backup    # manual backup inside the container
./deploy/aiptp.sh update    # rebuild with latest base images and restart
./deploy/aiptp.sh down
```

First visit shows the **admin setup screen** (server mode runs with
`AIPTP_AUTH=required`). Everything — price watching, automation rules, DCA
plans, corporate actions, backups — keeps running with nobody connected.

### Configuration (environment variables)

| Variable | Default | Purpose |
| --- | --- | --- |
| `AIPTP_AUTH` | `required` (image) / `disabled` (bare) | Login enforcement |
| `AIPTP_PORT` | `8420` | HTTP port |
| `AIPTP_DATA_DIR` | `/data` (image) / `./data` | DB, encrypted keys, backups |
| `AIPTP_MARKET_PROVIDERS` | `yahoo,stooq` | Ordered failover chain |
| `AIPTP_ALPHAVANTAGE_KEY` | — | Or store encrypted via Settings UI |
| `AIPTP_BACKUP_INTERVAL_HOURS` | `24` | Automatic SQLite backups (7 kept) |
| `AIPTP_WATCH_INTERVAL_SECONDS` | `15` | Price watch cadence |

### Corporate TLS-inspecting proxies

Build with your proxy's **full CA bundle** as a secret — never disable TLS
verification:

```bash
docker build --secret id=extra_ca,src=/path/to/ca-bundle.crt -f deploy/Dockerfile .
```

At runtime, mount the bundle and point `SSL_CERT_FILE` at it:

```yaml
    volumes:
      - /path/to/ca-bundle.crt:/etc/aiptp/ca.crt:ro
    environment:
      SSL_CERT_FILE: /etc/aiptp/ca.crt
```

### GPU passthrough

Uncomment the `deploy.resources.reservations.devices` block in
`deploy/compose.yaml` (NVIDIA container toolkit required). Used from M4 for
local AI inference.

### Backups

Automatic daily SQLite snapshots to `<data>/backups/` via the SQLite
online-backup API (safe on a live database), newest 7 kept. Manual:
Settings → "Back up now", `POST /api/v1/admin/backup`, or
`./deploy/aiptp.sh backup`. Restore = stop, replace `aiptp.db` with a
snapshot, start.
