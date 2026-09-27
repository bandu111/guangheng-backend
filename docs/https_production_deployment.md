# GuangHeng Production HTTPS Deployment

Deployment date: 2026-09-25  
Public endpoint: `https://43.155.204.194`  
Backend version during migration: `1.5.0`

## Architecture

```text
Flutter / Energy Companion
        |
        v
https://43.155.204.194:443
        |
        v
Nginx
        |
        v
http://127.0.0.1:8000
        |
        v
GuangHeng Backend Docker
```

MCP remains bound to `127.0.0.1:8001`. Home Assistant and Modbus are not
published by Nginx. The server explicitly returns 404 for `/mcp`, `/mcp/`,
`/ha`, and `/ha/`.

## Nginx

- Site configuration: `/etc/nginx/sites-available/guangheng`
- Enabled link: `/etc/nginx/sites-enabled/guangheng`
- WebSocket map: `/etc/nginx/conf.d/guangheng-upgrade.conf`
- ACME webroot: `/var/www/letsencrypt`
- Reverse proxy target: `http://127.0.0.1:8000`
- Request body limit: 32 MiB
- TLS protocols: TLS 1.2 and TLS 1.3
- HTTP behavior: ACME challenge is served locally; all other requests receive
  a 308 redirect to HTTPS.

## Certificate

The certificate is a public Let's Encrypt IP Address Certificate requested with
Certbot's `shortlived` profile. Staging issuance was completed before Production
issuance.

- Certbot: Snap package, version 5.8.0 at deployment time
- Certificate: `/etc/letsencrypt/live/43.155.204.194/fullchain.pem`
- Private key: `/etc/letsencrypt/live/43.155.204.194/privkey.pem`
- Renewal configuration: `/etc/letsencrypt/renewal/43.155.204.194.conf`
- Deploy hook: `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`

The deploy hook validates the Nginx configuration before reloading it. Certbot's
Snap timer checks renewal twice per day. `certbot renew --dry-run` was used to
validate staging renewal and deploy-hook execution.

## Monitoring

- Script: `/usr/local/sbin/check-guangheng-cert`
- Service: `guangheng-cert-monitor.service`
- Timer: `guangheng-cert-monitor.timer`
- Frequency: every six hours
- Alert condition: certificate has less than 72 hours remaining, certificate is
  unreadable, or Nginx configuration validation fails
- Logs: `journalctl -u guangheng-cert-monitor.service` and system log entries
  tagged `guangheng-cert-monitor` or `guangheng-cert-renewal`

## Network Surface

| Port | Exposure |
|---|---|
| 80 | Public; ACME and HTTPS redirect only |
| 443 | Public; Nginx HTTPS API |
| 8000 | Loopback only; Nginx upstream |
| 8001 | Loopback only; MCP |
| 8123 | Blocked on public interface; internal Home Assistant remains available |
| 502 | Loopback only; simulator Modbus endpoints |
| 18555 | Blocked on public interface; internal go2rtc process unchanged |
| 2375/2376 | Not listening |

Public-interface rules for Home Assistant and go2rtc are managed by:

- `/usr/local/sbin/guangheng-private-ports`
- `guangheng-private-ports.service`

These rules only target inbound traffic on `eth0`; Docker bridge and loopback
traffic are unaffected.

## Client Configuration

- Flutter Production: `https://43.155.204.194`
- Flutter Development: `http://127.0.0.1:8000`
- Android Release: no global cleartext allowance
- Android Debug: local development cleartext is scoped to localhost addresses
- iOS: `NSAllowsArbitraryLoads` removed; local-network access remains declared
- ESP32 Production: `https://43.155.204.194`
- ESP32 TLS: ESP-IDF certificate bundle with common-name/IP verification enabled
- ESP32 time: SNTP must establish trustworthy time before the first HTTPS call

## Firewall

TCP 80 and 443 must remain allowed in the Tencent Cloud security group. Ports
8000, 8001, 8123, 502, 18555, 2375, and 2376 must not be opened publicly.
Host-level rules additionally block public-interface access to 8123 and 18555.

## Rollback

Server-side migration backups are stored at:

`/opt/guangheng/backups/https-20260925-0324`

The directory includes the pre-migration Docker Compose configuration and a
server-side environment backup. The environment backup is sensitive and must
never be copied into documentation or logs.

Rollback sequence:

1. Restore the backed-up `docker-compose.yml` to `/opt/guangheng/server/`.
2. Recreate only `guangheng-api`; do not remove volumes or the `storage` folder.
3. Stop and disable `guangheng-private-ports.service` only if public Home
   Assistant access is intentionally being restored.
4. Restore the backed-up Nginx configuration or stop Nginx.
5. Re-test Backend health, Home Assistant reads, MCP loopback binding, and
   storage integrity.

Rollback must not delete SQLite files, Docker volumes, Home Assistant data,
simulator state, or MCP configuration.

## Secret Handling

This document intentionally excludes the private key, Home Assistant token,
model-provider credentials, Companion credentials, and server environment
values.
