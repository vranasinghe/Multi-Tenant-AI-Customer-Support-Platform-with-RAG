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

## Trusted ingress (client IPs behind Caddy)

The API trusts forwarding headers only from the addresses in `FORWARDED_ALLOW_IPS` (DEVELOPMENT.md
section 10). **While it is empty, every visitor appears to the API as Caddy**: the per-IP limits
(for example 10 logins a minute and 10 sign-ups an hour) are then shared by all visitors, and audit
records hold Caddy's network instead of the client's. Configure it before real users arrive.

Give Caddy a fixed address on a network that only it uses to reach the API. Choose a private subnet
that is unused on your server; there is no default. Create `docker-compose.ingress.yml` next to
`docker-compose.prod.yml` (`deploy/deploy.sh` picks it up):

```yaml
networks:
  ingress:
    ipam:
      config:
        - subnet: ${INGRESS_SUBNET:?choose an unused private subnet}
          ip_range: ${INGRESS_DYNAMIC_RANGE:?part of the subnet used for other containers}
services:
  caddy:
    networks:
      ingress:
        ipv4_address: ${CADDY_INGRESS_IP:?an address in the subnet but outside the dynamic range}
  api:
    networks: [default, ingress]
  web:
    networks: [default, ingress]
```

Add those three variables to `.env.production`, plus `FORWARDED_ALLOW_IPS` set to exactly the same
value as `CADDY_INGRESS_IP`. Caddy joins only `ingress`, so it reaches `api` from that address;
trusting a whole network would also trust every container on it. Other `docker compose` commands in
this guide need `-f docker-compose.ingress.yml` as well once the file exists.

Requirements this relies on:

- Only Caddy publishes ports. Do not publish the API, PostgreSQL, Redis or object storage.
- Caddy replaces client-supplied `X-Forwarded-*` headers. This is its default; do not add
  `trusted_proxies` to the Caddyfile unless another proxy sits in front of it.
- If a CDN or load balancer is added in front, review both Caddy's and the API's trusted lists.

After deploying, verify on the server: send a request with a made-up `X-Forwarded-For` from outside
and confirm the API still records your real network (for example in the session list after signing
in). None of this has been verified on a live deployment.

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

`deploy/deploy.sh` also takes a quiesced backup before upgrading a running install.

Restore into empty volumes only, then verify. Procedure and migration policy:
[RECOVERY.md](RECOVERY.md).

```bash
COMPOSE_PROJECT_NAME=acs-restore bash deploy/restore.sh ~/backups <stamp>
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

- **Memory budget** (container limits sum to about 8 GB; swap is a 2 GB safety net): Postgres 2.5 GB,
  worker 2 GB, api 1 GB, web 0.6 GB, storage 0.5 GB, redis 0.4 GB, beat 0.3 GB, maintenance 0.5 GB, caddy 0.2 GB.
  Limits are ceilings, not reservations, but they now reach the host's 8 GB: watch memory.
  The worker also has 2 CPUs, 128 PIDs and no extra swap, sized for `WORKER_CONCURRENCY=2`
  ([INGESTION.md §8](INGESTION.md)). Raising the concurrency needs `WORKER_MEMORY_LIMIT`,
  `WORKER_CPUS` and `WORKER_PIDS_LIMIT` raised with it, and this host has little room left.
- **Single server = single point of failure.** Reboots restart containers automatically
  (`restart: unless-stopped`), but there is no failover.
- **Moving to a real domain later:** change `SITE_HOST`, point DNS at the VPS, rebuild `web`.
  Nothing else changes.
- **DuckDNS** is a free third-party service; if it is down, the name stops resolving even though
  the server is fine. A purchased domain removes that dependency.
