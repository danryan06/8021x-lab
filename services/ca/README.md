# Certificate Authority adapters

The control plane talks to CA implementations through `CertificateAuthorityAdapter`:

| Adapter | Status | Notes |
|---------|--------|-------|
| `openssl` | Phase 0 | Local PEM tree under `CA_DATA_DIR` |
| `step-ca` | Stub | Smallstep API integration planned for Phase 2 |

Set `CA_ADAPTER=openssl` (default) or `CA_ADAPTER=step-ca` in `.env`.
