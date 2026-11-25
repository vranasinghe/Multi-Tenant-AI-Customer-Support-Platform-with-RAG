# Deploying everything on one Contabo VPS (no purchased domain)

Target: Cloud VPS 4 (4 vCPU, 8 GB RAM, 100 GB). One public origin, `https://<name>.duckdns.org`,
served by Caddy with an automatic Let's Encrypt certificate:

| Path                                                  | Goes to           |
| ----------------------------------------------------- | ----------------- |
| `/api/v1/*`, `/public/*`, `/widget/*`, `/healthz`, `/readyz` | FastAPI (`api`)   |
| everything else (including `/api/health`)             | Next.js (`web`)   |

Postgres, Redis and object storage are never exposed; only ports 22, 80 and 443 are open.
Because the dashboard and API share one origin, the `__Host-session` cookie and CORS work with
no extra configuration.

## 1. Free hostname (DuckDNS)

1. Sign in at <https://www.duckdns.org>, create a subdomain (e.g. `mychatbot`) and set its
   **current ip** to the VPS IPv4 address.
2. Your `SITE_HOST` is `mychatbot.duckdns.org`.

## 2. Prepare the server

```bash
ssh root@<vps-ip>
apt-get update && apt-get install -y git
git clone <your-repo-url> /root/app && cd /root/app      # or scp/rsync the project
bash deploy/setup-vps.sh deploy
```

Before running the script, make sure your SSH public key is in `/root/.ssh/authorized_keys`
(it is when you added the key in Contabo's panel). The script copies it to the `deploy` user,
then disables root and password SSH login. Reconnect as `deploy`:

```bash
ssh deploy@<vps-ip>
git clone <your-repo-url> ~/app && cd ~/app
```

## 3. Configure

```bash
cp .env.production.example .env.production
chmod 600 .env.production
nano .env.production
```

Fill in: `SITE_HOST`, `ACME_EMAIL`, all passwords/keys (generate each with
`openssl rand -base64 36 | tr -d '/+=' | cut -c1-40`), SMTP settings, and the AI provider keys.
Production refuses placeholder passwords, the `hash` embedding provider, the `demo` LLM and the
`log` email backend, so every one of those must be real.

## 4. Build the widget, then deploy

The API image bakes in `services/api/widget_assets`, which is committed to the repo. Only rebuild
it after changing `apps/widget`:

```bash
corepack enable && corepack pnpm install && corepack pnpm --filter @acs/widget build
```

Then:

```bash
bash deploy/deploy.sh
```

This builds the images (the first build takes several minutes), runs migrations, starts every
service and waits for `https://<SITE_HOST>/readyz`. Open `https://<SITE_HOST>` and register.

## 5. Backups

```bash
chmod +x deploy/backup.sh
crontab -e     # add:  0 3 * * * cd ~/app && bash deploy/backup.sh >> ~/backup.log 2>&1
```

Contabo's auto-backup is a paid add-on and is off for this VPS. Copy `~/backups` off the server
(`rclone` to Backblaze B2, Cloudflare R2 or Google Drive); a backup on the same disk is not enough.

Restore a database dump:

```bash
gunzip -c ~/backups/db-<stamp>.sql.gz | docker compose --env-file .env.production \
  -f docker-compose.prod.yml exec -T postgres psql -U platform_owner -d chatbot
```

## 6. Operations

```bash
C="docker compose --env-file .env.production -f docker-compose.prod.yml"
$C ps                         # status
$C logs -f --tail=100 api     # logs (also: worker, web, caddy)
git pull && bash deploy/deploy.sh   # update
```

Changing `SITE_HOST` requires rebuilding `web` (`NEXT_PUBLIC_API_URL` is baked into the bundle).

## 7. Widget on customer sites

Use `https://<SITE_HOST>/widget/v1/loader.js` as the script `src` (see `docs/WIDGET_DEPLOYMENT.md`).
Each customer site origin must be added and verified in the dashboard.

## Notes and limits

- **Memory budget** (container limits sum to about 7 GB; swap is a 2 GB safety net): Postgres 2.5 GB,
  worker 1.5 GB, api 1 GB, web 0.6 GB, storage 0.5 GB, redis 0.4 GB, beat 0.3 GB, caddy 0.2 GB.
  Lower `WORKER_CONCURRENCY` if crawls cause memory pressure.
- **Single server = single point of failure.** Reboots restart containers automatically
  (`restart: unless-stopped`), but there is no failover.
- **Moving to a real domain later:** change `SITE_HOST`, point DNS at the VPS, rebuild `web`.
  Nothing else changes.
- **DuckDNS** is a free third-party service; if it is down, the name stops resolving even though
  the server is fine. A purchased domain removes that dependency.
