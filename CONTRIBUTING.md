# Contributing to 802.1X Lab

Thanks for helping improve an engineer-friendly 802.1X lab platform.

## Development setup

See [docs/developer-setup.md](docs/developer-setup.md).

## Guidelines

- Keep changes focused. Prefer small, reviewable pull requests.
- This project is a sandbox on top of FreeRADIUS — do not reimplement a RADIUS server.
- Do not add Active Directory, LDAP, cloud IdP, or vendor config generators without an agreed design.
- Never commit secrets, shared secrets, private keys, or real `.env` files.
- Match existing structure: FastAPI backend, React/Vite frontend, Docker Compose services.
- Document intentional complexity (EAP, certs, RADIUS attributes) so Simple Mode can stay simple.

## Before you open a PR

Run the same checks CI runs (see [docs/developer-setup.md](docs/developer-setup.md#tests-linting-and-ci)):

```bash
make lint      # ruff check backend
make test      # pytest backend
cd frontend && npm run build   # tsc --noEmit + Vite build
```

## Pull requests

1. Fork (or branch) from `main`.
2. Make your change with clear commits.
3. Update docs when behavior or setup changes — including the
   [concepts](docs/concepts.md) / [usage](docs/usage.md) guides when you add or
   change a user-facing feature.
4. Open a PR describing *why* the change exists and how to test it.

## Code of conduct

Be respectful and constructive. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions are licensed under the Apache License 2.0.
