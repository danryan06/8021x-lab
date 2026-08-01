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
| `reload.request` | Touch file — entrypoint runs `radmin hup` / SIGHUP |
| `logs/auth.log` | Linelog output tailed by the backend ingestion worker |
