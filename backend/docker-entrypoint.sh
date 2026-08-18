#!/bin/sh
# Apply schema + seed before the API listens so a fresh install never needs
# `alembic upgrade head` as an operator step.
set -eu
python -m app.runtime_setup
exec "$@"
