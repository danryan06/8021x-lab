# FreeRADIUS templates

Files rendered or installed into the FreeRADIUS container.

| File | Role |
|------|------|
| `clients.conf.j2` | Jinja2 template — backend renders lab NAS clients to `clients.dot1x.conf` |
| `linelog_dot1x` | Pinned `DOT1X\|...` linelog module installed by the FreeRADIUS entrypoint |

## Runtime volume (`/etc/freeradius/dot1x-lab`)

| Path | Role |
|------|------|
| `clients.dot1x.conf` | Rendered clients included from stock `clients.conf` |
| `reload.request` | Touch file — entrypoint runs `radmin hup` / SIGHUP (module/virtual-server reload only) |
| `restart.request` | Touch file — entrypoint does a controlled in-container restart (needed for client and CA/trust changes, which HUP does not apply) |
| `trusted/ca-bundle.pem` | Published lab CA trust bundle for EAP-TLS client verification |
| `trusted/crl-bundle.pem` | Published CRL bundle; enforced only when `FREERADIUS_ENFORCE_CRL=yes` |
| `certs/ca.pem` | EAP server CA exported for backend `eapol_test` |
| `logs/auth.log` | Linelog output tailed by the backend ingestion worker |
| `health.status` | Heartbeat written by the entrypoint, polled by `/api/health` |
