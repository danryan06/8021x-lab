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

The NAS must reach the host IP on UDP 1812/1813. On Docker Desktop (macOS/Windows), publish those ports and point the RADIUS client at the host. On Linux, bridge networking usually works with the host's LAN IP; host networking is an advanced option for lab appliances.

Update RADIUS clients in the UI (or API) to match the NAS source IP and shared secret.

## Future appliance targets

Not implemented yet:

- Ubuntu Server LTS VM / OVA
- Proxmox VM template
- Raspberry Pi image
- Bare metal Linux

Design intent: same Compose stack under the hood; appliance UX should not require Docker knowledge.

## Security disclaimer

This project is for **labs and education**. Default credentials, published DB ports, and simplified PKI are intentional for learning — not for production.
