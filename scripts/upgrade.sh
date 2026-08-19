#!/usr/bin/env bash
# 802.1X Lab — in-place upgrade for 64-bit Linux (incl. Raspberry Pi OS 64-bit).
#
#   curl -fsSL https://raw.githubusercontent.com/danryan06/8021x-lab/main/scripts/upgrade.sh | bash
#
# Keeps your .env, database, RADIUS logs, certificates, and lab users.
# For a clean lab (wipe data, keep .env), use install.sh instead.
#
# What it does:
#   1. Finds the existing checkout (~/8021x-lab, DOT1X_LAB_DIR, or the current directory)
#   2. Pulls the latest code
#   3. Rebuilds and restarts (schema updates apply on backend start)
#
# Options (environment variables):
#   DOT1X_LAB_DIR=/path      install directory   (default: $HOME/8021x-lab)
#   DOT1X_LAB_BRANCH=name    git branch to pull  (default: main)
#
# Prefer to read before you run? Download it first:
#   curl -fsSLO https://raw.githubusercontent.com/danryan06/8021x-lab/main/scripts/upgrade.sh
#   less upgrade.sh && bash upgrade.sh

set -euo pipefail

BRANCH="${DOT1X_LAB_BRANCH:-main}"
INSTALL_DIR="${DOT1X_LAB_DIR:-$HOME/8021x-lab}"
CURRENT_USER="${USER:-$(id -un)}"

info() { printf '\033[1;34m[802.1x-lab]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[802.1x-lab]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[802.1x-lab]\033[0m ERROR: %s\n' "$*" >&2; exit 1; }

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=""
elif command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
else
  SUDO=""
fi

install_hint() {
  printf '  curl -fsSL https://raw.githubusercontent.com/danryan06/8021x-lab/main/scripts/install.sh | bash\n'
}

# --- platform checks ---------------------------------------------------------
if [[ "$(uname -s)" != "Linux" ]]; then
  die "This upgrade script supports Linux (incl. Raspberry Pi OS 64-bit) only.
On macOS/Windows, from the project folder: git pull && make up"
fi

command -v git >/dev/null 2>&1 \
  || die "git is not installed. Run the installer first:
$(install_hint)"
command -v docker >/dev/null 2>&1 \
  || die "Docker is not installed. Run the installer first:
$(install_hint)"

if docker info >/dev/null 2>&1; then
  :
elif [[ -n "${SUDO}" ]] && ${SUDO} docker info >/dev/null 2>&1; then
  :
else
  die "The Docker daemon is not running. Start it (sudo systemctl start docker) and re-run."
fi

# --- find the existing checkout ----------------------------------------------
if [[ -f docker-compose.yml && -d scripts && -d backend ]]; then
  INSTALL_DIR="$(pwd)"
  info "Using the existing checkout in ${INSTALL_DIR}."
elif [[ -f "${INSTALL_DIR}/docker-compose.yml" && -d "${INSTALL_DIR}/backend" ]]; then
  info "Upgrading the existing install in ${INSTALL_DIR}..."
else
  die "No 802.1X Lab install found at ${INSTALL_DIR}.
Run the installer first:
$(install_hint)"
fi
cd "${INSTALL_DIR}"

# --- pull latest code --------------------------------------------------------
if [[ -d .git ]]; then
  info "Pulling the latest code (branch ${BRANCH})..."
  git fetch origin "${BRANCH}" \
    && git checkout "${BRANCH}" \
    && git merge --ff-only "origin/${BRANCH}" \
    || warn "Could not fast-forward to origin/${BRANCH} (local changes?). Continuing with the current code."
else
  warn "This checkout is not a git repository; leaving the current code as-is."
fi

if [[ ! -f .env ]]; then
  warn "No .env found — creating one from .env.example (fresh SECRET_KEY)."
  cp .env.example .env
  SECRET="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" .env
else
  info "Keeping your existing .env, database, RADIUS logs, and certificates."
fi

# Run a command with a working docker client (same fallbacks as install.sh).
run_with_docker() {
  if docker info >/dev/null 2>&1; then
    "$@"
  elif getent group docker | grep -qw "${CURRENT_USER}"; then
    info "Using 'sg docker' (group not active in this session yet)..."
    sg docker -c "$(printf '%q ' "$@")"
  else
    warn "Using sudo for Docker (docker group unavailable)."
    ${SUDO} "$@"
  fi
}

# --- rebuild and restart (volumes are left alone) ----------------------------
info "Rebuilding and restarting the lab (data is kept)..."
run_with_docker ./scripts/bootstrap.sh

HOST_IP="$(./scripts/detect-host-ip.sh 2>/dev/null || true)"
ADMIN_USER="$(grep '^ADMIN_USERNAME=' .env | cut -d= -f2- || true)"
echo
info "────────────────────────────────────────────────────────"
info "802.1X Lab is upgraded and running."
info "  UI:        http://localhost:3000"
if [[ -n "${HOST_IP}" ]]; then
  info "  UI (LAN):  http://${HOST_IP}:3000"
fi
info "  API docs:  http://localhost:8000/docs"
info "  Login:     ${ADMIN_USER:-admin} / ADMIN_PASSWORD from ${INSTALL_DIR}/.env"
info "Users, events, certificates, and RADIUS logs were kept."
info "For a clean lab instead, re-run the installer (it wipes data, keeps .env)."
