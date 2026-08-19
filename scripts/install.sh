#!/usr/bin/env bash
# 802.1X Lab — one-line installer for 64-bit Linux (incl. Raspberry Pi OS 64-bit).
#
#   curl -fsSL https://raw.githubusercontent.com/danryan06/8021x-lab/main/scripts/install.sh | bash
#
# What it does (safe to re-run; a re-run is a *clean* reinstall):
#   1. Checks the platform (Linux, 64-bit; warns off 32-bit ARM)
#   2. Installs git, make, curl and Docker Engine + Compose if missing
#   3. Adds your user to the docker group (fully active after your next login)
#   4. Clones the repo to ~/8021x-lab, or updates an existing checkout
#   5. Creates .env with a random SECRET_KEY on first install (kept on re-run)
#   6. Deletes previous lab data volumes (database, RADIUS logs, CA)
#   7. Runs scripts/bootstrap.sh (build images, start services; schema + seed run on backend start)
#
# This is a clean reinstall. To keep users/events/certs/logs, use upgrade.sh:
#   curl -fsSL https://raw.githubusercontent.com/danryan06/8021x-lab/main/scripts/upgrade.sh | bash
#
# Options (environment variables):
#   DOT1X_LAB_DIR=/path      install directory   (default: $HOME/8021x-lab)
#   DOT1X_LAB_BRANCH=name    git branch          (default: main)
#   DOT1X_LAB_REPO=url       repository URL      (default: official repo)
#
# Prefer to read before you run? Download it first:
#   curl -fsSLO https://raw.githubusercontent.com/danryan06/8021x-lab/main/scripts/install.sh
#   less install.sh && bash install.sh

set -euo pipefail

REPO_URL="${DOT1X_LAB_REPO:-https://github.com/danryan06/8021x-lab.git}"
BRANCH="${DOT1X_LAB_BRANCH:-main}"
INSTALL_DIR="${DOT1X_LAB_DIR:-$HOME/8021x-lab}"
CURRENT_USER="${USER:-$(id -un)}"

info() { printf '\033[1;34m[802.1x-lab]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[802.1x-lab]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[802.1x-lab]\033[0m ERROR: %s\n' "$*" >&2; exit 1; }

# --- sudo handling -----------------------------------------------------------
if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=""
else
  command -v sudo >/dev/null 2>&1 \
    || die "This installer needs sudo for package installs (or run it as root)."
  SUDO="sudo"
fi

# --- platform checks ---------------------------------------------------------
if [[ "$(uname -s)" != "Linux" ]]; then
  die "This installer supports Linux (incl. Raspberry Pi OS 64-bit) only.
On macOS/Windows, install Docker Desktop and follow docs/installation.md."
fi

ARCH="$(uname -m)"
case "${ARCH}" in
  x86_64 | aarch64) ;;
  armv7l | armv6l)
    die "32-bit OS detected (${ARCH}). The lab needs a 64-bit OS — on a Raspberry Pi,
reinstall with 64-bit Raspberry Pi OS or 64-bit Ubuntu (see docs/installation.md)."
    ;;
  *)
    warn "Untested architecture '${ARCH}' — continuing, but the Docker images may not exist for it."
    ;;
esac

HAVE_APT=0
if command -v apt-get >/dev/null 2>&1; then
  HAVE_APT=1
  export DEBIAN_FRONTEND=noninteractive
fi

# --- base tools (git, make, curl) ---------------------------------------------
need_pkgs=()
command -v git >/dev/null 2>&1 || need_pkgs+=(git)
command -v make >/dev/null 2>&1 || need_pkgs+=(make)
command -v curl >/dev/null 2>&1 || need_pkgs+=(curl)
if [[ ${#need_pkgs[@]} -gt 0 ]]; then
  if [[ ${HAVE_APT} -eq 1 ]]; then
    info "Installing missing tools: ${need_pkgs[*]}"
    ${SUDO} apt-get update -qq
    ${SUDO} apt-get install -y -qq "${need_pkgs[@]}" ca-certificates
  else
    die "Missing: ${need_pkgs[*]}. Install them with your distro's package manager, then re-run."
  fi
fi

# --- Docker Engine + Compose ---------------------------------------------------
if command -v docker >/dev/null 2>&1; then
  info "Docker is already installed."
else
  info "Installing Docker Engine + Compose via get.docker.com (this takes a few minutes)..."
  curl -fsSL https://get.docker.com | ${SUDO} sh
fi

if ! ${SUDO} docker compose version >/dev/null 2>&1; then
  if [[ ${HAVE_APT} -eq 1 ]]; then
    info "Installing the Docker Compose plugin..."
    ${SUDO} apt-get install -y -qq docker-compose-plugin
  else
    die "Docker Compose v2 is missing. Install the docker-compose-plugin package, then re-run."
  fi
fi

# Make sure the daemon is up (no-op on non-systemd hosts).
${SUDO} systemctl enable --now docker >/dev/null 2>&1 || true
${SUDO} docker info >/dev/null 2>&1 \
  || die "The Docker daemon is not running. Start it (sudo systemctl start docker) and re-run."

# --- docker group (avoids needing sudo for docker in future sessions) ----------
NEED_RELOGIN=0
if [[ -n "${SUDO}" ]] && ! docker info >/dev/null 2>&1; then
  if ! getent group docker | grep -qw "${CURRENT_USER}"; then
    info "Adding ${CURRENT_USER} to the docker group (active after your next login)..."
    ${SUDO} usermod -aG docker "${CURRENT_USER}"
  fi
  NEED_RELOGIN=1
fi

# --- get the code ---------------------------------------------------------------
if [[ -f docker-compose.yml && -d scripts && -d backend ]]; then
  # Already running from inside a checkout — use it.
  INSTALL_DIR="$(pwd)"
  info "Using the existing checkout in ${INSTALL_DIR}."
elif [[ -d "${INSTALL_DIR}/.git" ]]; then
  info "Updating the existing install in ${INSTALL_DIR}..."
  git -C "${INSTALL_DIR}" pull --ff-only \
    || warn "Could not fast-forward (local changes?). Continuing with the current code."
else
  info "Downloading 802.1X Lab to ${INSTALL_DIR}..."
  git clone --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
fi
cd "${INSTALL_DIR}"

# --- configuration ---------------------------------------------------------------
if [[ -f .env ]]; then
  info "Keeping your existing .env configuration."
else
  info "Creating .env (with a freshly generated SECRET_KEY)..."
  cp .env.example .env
  SECRET="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" .env
fi

# Run a command with a working docker client (same fallbacks as bootstrap).
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

# --- wipe previous lab data (logs, events, users, certs) -------------------------
# Volumes survive image rebuilds. Without this, a re-install keeps Auth Events
# and FreeRADIUS auth.log from the last run. Keep that data with upgrade.sh.
info "Removing any previous lab data (database, RADIUS logs, certificates)..."
run_with_docker ./scripts/reset-lab.sh

# --- build, start (schema + seed happen inside the backend container) -------------
run_with_docker ./scripts/bootstrap.sh

# --- done ---------------------------------------------------------------------------
HOST_IP="$(./scripts/detect-host-ip.sh 2>/dev/null || true)"
ADMIN_USER="$(grep '^ADMIN_USERNAME=' .env | cut -d= -f2- || true)"
echo
info "────────────────────────────────────────────────────────"
info "802.1X Lab is installed and running."
info "  UI:        http://localhost:3000"
if [[ -n "${HOST_IP}" ]]; then
  info "  UI (LAN):  http://${HOST_IP}:3000"
fi
info "  API docs:  http://localhost:8000/docs"
info "  Login:     ${ADMIN_USER:-admin} / ADMIN_PASSWORD from ${INSTALL_DIR}/.env (default: admin)"
info "Change ADMIN_PASSWORD in .env before showing this to anyone else."
info "Next steps: docs/usage.md (how-to) and docs/concepts.md (what/why)."
if [[ "${NEED_RELOGIN}" -eq 1 ]]; then
  warn "Log out and back in (or reboot) so 'docker' works without sudo in new sessions."
fi
info "Re-run this installer for a clean reinstall (wipes lab data, keeps .env)."
info "To update without wiping: curl -fsSL https://raw.githubusercontent.com/danryan06/8021x-lab/main/scripts/upgrade.sh | bash"
