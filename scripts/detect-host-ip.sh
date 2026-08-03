#!/usr/bin/env bash
# Detect the host's primary LAN/DHCP IPv4 for RADIUS advertise targeting.
set -euo pipefail

detect() {
  local found=""
  if command -v ip >/dev/null 2>&1; then
    found="$(ip -4 route get 1.1.1.1 2>/dev/null \
      | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
    # Fall through to hostname -I when there is no default route (VPN-only
    # hosts etc.) instead of returning empty here.
  fi
  if [[ -z "${found}" ]] && command -v hostname >/dev/null 2>&1; then
    found="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  if [[ -z "${found}" ]]; then
    return 1
  fi
  echo "${found}"
}

IP="$(detect | head -n1 | tr -d '[:space:]')"
if [[ -z "${IP}" || "${IP}" == "127.0.0.1" ]]; then
  exit 1
fi
echo "${IP}"
