# Kara — Production Deployment Guide

Target server: **Ubuntu 24.04 LTS** · IP `85.198.10.243` · Domain `portal.pakhshmarket.com`

Architecture: **Nginx → Gunicorn → Django → PostgreSQL**  
Background: **kara-scheduler** (APScheduler) · **kara-bot** (Bale, optional)

Repository: https://github.com/qashqaeii/Kara

---

## 1. Server preparation

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3 python3-venv python3-pip nginx postgresql postgresql-contrib certbot python3-certbot-nginx ufw curl
```

### Firewall (UFW)

Only SSH, HTTP, and HTTPS should be public. PostgreSQL and Gunicorn stay on localhost.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Do **not** expose ports `5432` (PostgreSQL) or `8000` (Gunicorn).

---

## 2. System user and directories

Run once as **root**:

```bash
sudo bash /opt/kara/deploy/setup-server.sh
```

Or before cloning:

```bash
git clone https://github.com/qashqaeii/Kara.git /opt/kara
sudo bash /opt/kara/deploy/setup-server.sh
```

This creates:

| Path | Purpose | Owner |
|---|---|---|
| `/opt/kara` | Application code + venv | `kara:kara` |
| `/var/lib/kara/staticfiles` | `collectstatic` output | `kara:kara` |
| `/var/lib/kara/media` | Uploaded media | `kara:kara` |
| `/var/lib/kara/cache` | File-based Django cache | `kara:kara` |
| `/var/log/kara` | Application logs | `kara:kara` |

`setup-server.sh` also installs `/etc/sudoers.d/kara-deploy` so user `kara` can restart Kara services without a password (restart/reload only).

---

## 3. PostgreSQL

```bash
sudo -u postgres psql <<'SQL'
CREATE USER kara WITH PASSWORD 'CHANGE_ME_STRONG_PASSWORD';
CREATE DATABASE kara OWNER kara;
GRANT ALL PRIVILEGES ON DATABASE kara TO kara;
SQL
```

PostgreSQL listens on `127.0.0.1` only (default on Ubuntu).

---

## 4. Clone application

```bash
sudo -u kara git clone https://github.com/qashqaeii/Kara.git /opt/kara
cd /opt/kara
sudo -u kara python3 -m venv .venv
sudo -u kara .venv/bin/pip install -r requirements.txt
```

---

## 5. Environment file

```bash
sudo -u kara cp .env.example .env
sudo -u kara nano .env
```

**Required production values:**

| Variable | Example |
|---|---|
| `DJANGO_SECRET_KEY` | random 50+ char string |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `portal.pakhshmarket.com,85.198.10.243` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://portal.pakhshmarket.com` |
| `DATABASE_ENGINE` | `postgresql` |
| `POSTGRES_DB` | `kara` |
| `POSTGRES_USER` | `kara` |
| `POSTGRES_PASSWORD` | (from step 3) |
| `POSTGRES_HOST` | `127.0.0.1` |
| `DJANGO_STATIC_ROOT` | `/var/lib/kara/staticfiles` |
| `DJANGO_MEDIA_ROOT` | `/var/lib/kara/media` |
| `KARA_LOG_DIR` | `/var/log/kara` |
| `KARA_CACHE_DIR` | `/var/lib/kara/cache` |
| `KARA_CREDENTIALS_FILE` | `/var/lib/kara/credentials.txt` |
| `KARA_COOKIE_FILE` | `/var/lib/kara/cookies.txt` |
| `KARA_USERNAME` / `KARA_PASSWORD` | Kara API credentials |
| `KARA_DISABLE_AUTO_REFRESH` | `1` (web service) |

### SSL phases

| Phase | When | `.env` settings |
|---|---|---|
| **1 — pre-Certbot** | DNS ready, HTTP works | `DJANGO_SECURE_SSL_REDIRECT=False` |
| **2 — post-Certbot** | HTTPS certificate active | `DJANGO_SECURE_SSL_REDIRECT=True` |

Always in production (both phases):

```env
DJANGO_SESSION_COOKIE_SECURE=True
DJANGO_CSRF_COOKIE_SECURE=True
DJANGO_USE_X_FORWARDED_HOST=True
```

`python manage.py check --deploy` may show **W008** until phase 2 (`SECURE_SSL_REDIRECT=True`). This is expected — do not silence it.

Generate secret key:

```bash
/opt/kara/.venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Place runtime secrets outside git:

```bash
sudo -u kara nano /var/lib/kara/credentials.txt
# username=...
# password=...
sudo chmod 600 /var/lib/kara/credentials.txt
```

---

## 6. Django bootstrap

```bash
cd /opt/kara
sudo -u kara .venv/bin/python manage.py check
sudo -u kara .venv/bin/python manage.py migrate
sudo -u kara .venv/bin/python manage.py collectstatic --noinput
sudo -u kara .venv/bin/python manage.py createsuperuser
```

---

## 7. systemd services

```bash
sudo cp /opt/kara/deploy/systemd/kara-web.service /etc/systemd/system/
sudo cp /opt/kara/deploy/systemd/kara-scheduler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kara-web kara-scheduler
```

**Do not enable `kara-bot` until `BALE_BOT_TOKEN` is set in `.env`.** Web and scheduler are independent of the bot.

```bash
# Only after BALE_BOT_TOKEN is configured:
sudo cp /opt/kara/deploy/systemd/kara-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kara-bot
```

| Service | Role |
|---|---|
| `kara-web` | Gunicorn HTTP — no scheduler, no bot |
| `kara-scheduler` | APScheduler sync (`KARA_RUN_SCHEDULER=1`) |
| `kara-bot` | Bale polling — optional, separate process |

---

## 8. Nginx

```bash
sudo cp /opt/kara/deploy/nginx/portal.pakhshmarket.com.conf /etc/nginx/sites-available/kara
sudo ln -sf /etc/nginx/sites-available/kara /etc/nginx/sites-enabled/kara
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

---

## 9. SSL with Let's Encrypt

Ensure DNS `portal.pakhshmarket.com` → `85.198.10.243`.

```bash
sudo certbot --nginx -d portal.pakhshmarket.com
```

After certificate is active, update `/opt/kara/.env`:

```env
DJANGO_SECURE_SSL_REDIRECT=True
```

Then redeploy:

```bash
sudo -u kara bash /opt/kara/deploy/deploy.sh
```

Test renewal:

```bash
sudo certbot renew --dry-run
curl -fsS https://portal.pakhshmarket.com/health/
```

---

## 10. Deploy updates

Application deploy (as `kara`):

```bash
sudo -u kara bash /opt/kara/deploy/deploy.sh
```

Service restart (if passwordless sudo not configured):

```bash
sudo bash /opt/kara/deploy/restart-services.sh
```

`deploy.sh` runs: `git pull` → `pip install` → `check` → `migrate` → `collectstatic` → restart (via sudo if allowed).

---

## 11. Health & monitoring

| Endpoint | Purpose |
|---|---|
| `https://portal.pakhshmarket.com/health/` | DB connectivity |
| `https://portal.pakhshmarket.com/healthz/` | Alias |

```bash
sudo journalctl -u kara-web -u kara-scheduler --since today
sudo tail -f /var/log/kara/kara.log
```

---

## 12. Troubleshooting

| Symptom | Check |
|---|---|
| 502 Bad Gateway | `systemctl status kara-web` |
| CSRF errors | `DJANGO_CSRF_TRUSTED_ORIGINS`, Nginx `X-Forwarded-Proto` |
| Duplicate sync jobs | Only `kara-scheduler` has `KARA_RUN_SCHEDULER=1` |
| Static 404 | `collectstatic`, Nginx alias `/var/lib/kara/staticfiles/` |
| Deploy cannot restart | Run `setup-server.sh` or `sudo bash deploy/restart-services.sh` |
| `check --deploy` W008 | Set `DJANGO_SECURE_SSL_REDIRECT=True` after Certbot |

---

## Git security

Never commit: `.env`, `cookies.txt`, `credentials.txt`, `db.sqlite3`, private keys, tokens. All are listed in `.gitignore`.
