#!/usr/bin/env bash
# Detect the host's primary LAN/DHCP IPv4 for RADIUS advertise targeting.
set -euo pipefail

detect() {
  if command -v ip >/dev/null 2>&1; then
    ip -4 route get 1.1.1.1 2>/dev/null \
      | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}'
    return 0
  fi
  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{print $1}'
    return 0
  fi
  return 1
}

IP="$(detect | head -n1 | tr -d '[:space:]')"
if [[ -z "${IP}" || "${IP}" == "127.0.0.1" ]]; then
  exit 1
fi
echo "${IP}"
