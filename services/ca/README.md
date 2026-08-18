# Certificate Authority adapters

The control plane talks to CA implementations through the
`CertificateAuthorityAdapter` protocol
(`backend/app/integrations/ca/base.py`):

- `ensure_root(lab_id, common_name)` — create/return the per-lab root CA
- `issue_client_cert(lab_id, identity, days)` — issue an EAP-TLS client cert
- `revoke(lab_id, cert_ref)` — revoke an issued certificate
- `generate_crl(lab_id)` — (re)generate the CRL from the CA database

| Adapter | Status | Notes |
|---------|--------|-------|
| `openssl` | Active (default) | Local PEM tree under `CA_DATA_DIR`, backed by a per-lab openssl CA database. Optional intermediate CA (`POST /ca/ensure-intermediate`) so client certs are not signed by the root. |
| `step-ca` | HTTP client | Talks to a running Smallstep CA (`STEP_CA_URL`, `STEP_CA_TOKEN`) via `/root` and `/1.0/sign`. Not started by Compose. |

Set `CA_ADAPTER=openssl` (default) or `CA_ADAPTER=step-ca` in `.env`. step-ca also
needs `STEP_CA_URL` and a provisioner token in `STEP_CA_TOKEN`.

## openssl adapter details

Each lab gets its own directory under `CA_DATA_DIR/<lab_id>/`:

```text
certs/root.crt          Root CA certificate (trust anchor)
certs/intermediate.crt  Optional intermediate (signs clients once created)
private/root.key        Root CA private key
private/intermediate.key Intermediate key
certs/<identity>.crt    Issued client certificates
private/<identity>.key  Client private keys
certs/<identity>.p12    PKCS#12 bundle (empty passphrase, for device import)
db/index.txt            openssl CA database of certs the *root* signed
db-int/index.txt        Database of certs the *intermediate* signed
db/newcerts/            Copies of issued certs, named by serial
db/serial, db/crlnumber Monotonic counters
openssl.cnf             Generated root CA config
intermediate.cnf        Generated intermediate CA config
crl.pem                 Current CRL (root, plus intermediate when present)
```

Certificates are signed with `openssl ca` (not `x509 -req`) so every issue is
recorded in `index.txt`. That database is what makes real revocation possible:
`revoke()` runs `openssl ca -revoke` and `generate_crl()` runs
`openssl ca -gencrl`. See [../../docs/concepts.md](../../docs/concepts.md) for the
"what and why" of certificates, CAs, and CRLs, and
[../../docs/architecture.md](../../docs/architecture.md) for how trust and the CRL
are published into FreeRADIUS.

> Certificates issued before the CA-database change (older `x509 -req` path) are
> not tracked in `index.txt` and cannot be CRL-revoked; re-issue them to bring
> them under revocation management.
