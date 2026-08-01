# Deployment

## Primary: Docker Compose

```bash
cp .env.example .env
# Edit secrets before any non-lab use
docker compose up -d
docker compose exec backend alembic upgrade head
```

Published ports (default):

| Port | Service |
|------|---------|
| 3000 | Web UI |
| 8000 | API |
| 5432 | PostgreSQL (dev convenience) |
| 1812/udp, 1813/udp | RADIUS auth/acct |

### Reaching FreeRADIUS from a real NAS

1. Set the lab **RADIUS target** in the UI (Dashboard → RADIUS target):
   - **Auto** picks up the host DHCP/LAN IP via bootstrap (`RADIUS_ADVERTISE_IP` / `host-ip` file)
   - **Manual** pins a specific IPv4 if DHCP is wrong or you use a VIP
2. On the NAS/WLC, point RADIUS at that advertise IP, UDP **1812** (auth) / **1813** (acct).
3. In **RADIUS Clients**, add the NAS **source** IP/CIDR + shared secret so FreeRADIUS accepts it.

On Docker Desktop (macOS/Windows), published ports map to the host — use the host LAN IP as the target. Compose containers cannot see the host DHCP address by themselves; `make bootstrap` / `scripts/detect-host-ip.sh` writes it in for Auto mode.

## Future appliance targets

Not implemented yet:

- Ubuntu Server LTS VM / OVA
- Proxmox VM template
- Raspberry Pi image
- Bare metal Linux

Design intent: same Compose stack under the hood; appliance UX should not require Docker knowledge.

## Security disclaimer

This project is for **labs and education**. Default credentials, published DB ports, and simplified PKI are intentional for learning — not for production.
