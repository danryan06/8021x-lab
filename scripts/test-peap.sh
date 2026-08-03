#!/usr/bin/env bash
# Phase 1 PEAP smoke test against a running Compose stack.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API="${API:-http://localhost:8000/api}"
ADMIN_USER="${ADMIN_USERNAME:-admin}"
ADMIN_PASS="${ADMIN_PASSWORD:-admin}"
RADIUS_HOST="${RADIUS_HOST:-127.0.0.1}"
RADIUS_SECRET="${RADIUS_SECRET:-testing123}"
TEST_USER="${TEST_USER:-peapuser}"
TEST_PASS="${TEST_PASS:-PeapTest123!}"

echo "Logging in..."
TOKEN="$(curl -fsS -X POST "$API/auth/login" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "username=${ADMIN_USER}&password=${ADMIN_PASS}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"

AUTH="Authorization: Bearer ${TOKEN}"

LAB_ID="$(curl -fsS -H "$AUTH" "$API/labs" | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["id"])')"
echo "Using lab ${LAB_ID}"

echo "Ensuring RADIUS client (lab documentation / file sync)..."
CLIENT_ID="$(curl -fsS -H "$AUTH" "$API/clients" | python3 -c "import sys,json; c=[x for x in json.load(sys.stdin) if x['name']=='peap-test-nas']; print(c[0]['id'] if c else '')")"
if [[ -z "${CLIENT_ID}" ]]; then
  curl -fsS -X POST "$API/clients" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"lab_id\":\"${LAB_ID}\",\"name\":\"peap-test-nas\",\"ip_address\":\"10.255.255.1\",\"shared_secret\":\"nas-secret\",\"device_type\":\"test\",\"enabled\":true}" \
    >/dev/null
fi

echo "Ensuring PEAP test user ${TEST_USER}..."
# Idempotent: update password if the user already exists from a prior run.
EXISTING_ID="$(curl -fsS -H "$AUTH" "$API/users" | python3 -c "import sys,json; u=[x for x in json.load(sys.stdin) if x['username']=='${TEST_USER}']; print(u[0]['id'] if u else '')")"
if [[ -n "${EXISTING_ID}" ]]; then
  curl -fsS -X PATCH "$API/users/${EXISTING_ID}" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"password\":\"${TEST_PASS}\",\"status\":\"active\"}" >/dev/null
else
  curl -fsS -X POST "$API/users" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"lab_id\":\"${LAB_ID}\",\"username\":\"${TEST_USER}\",\"password\":\"${TEST_PASS}\",\"groups\":[\"lab\"],\"status\":\"active\"}" \
    >/dev/null
fi

# Preferred path: run eapol_test inside the backend container, which already
# ships it (no host install, works on macOS/Windows Docker Desktop too).
# Values are passed as environment variables, never interpolated into the
# inner script, so quotes in TEST_USER/TEST_PASS cannot break it.
run_in_backend() {
  docker compose exec -T \
    -e TEST_USER="${TEST_USER}" \
    -e TEST_PASS="${TEST_PASS}" \
    -e RADIUS_SECRET="${RADIUS_SECRET}" \
    backend sh -c '
      set -e
      IP="$(python3 -c "import socket; print(socket.gethostbyname(\"freeradius\"))")"
      CONF="$(mktemp /tmp/dot1x-peap.XXXXXX.conf)"
      trap "rm -f \"$CONF\"" EXIT
      {
        echo "network={"
        echo "  key_mgmt=WPA-EAP"
        echo "  eap=PEAP"
        printf "  identity=\"%s\"\n" "$TEST_USER"
        printf "  password=\"%s\"\n" "$TEST_PASS"
        echo "  phase2=\"auth=MSCHAPV2\""
        echo "  ca_cert=\"/var/lib/dot1x-lab/freeradius/certs/ca.pem\""
        echo "}"
      } >"$CONF"
      eapol_test -c "$CONF" -a "$IP" -p 1812 -s "$RADIUS_SECRET" -r 1
    '
}

run_on_host() {
  local eapol_bin ca_pem conf
  eapol_bin="$(command -v eapol_test || command -v eapoltest)"
  ca_pem="/tmp/dot1x-ca.pem"
  if ! docker compose cp freeradius:/etc/freeradius/3.0/certs/ca.pem "$ca_pem" 2>/dev/null; then
    docker compose exec -T freeradius cat /etc/freeradius/3.0/certs/ca.pem >"$ca_pem"
  fi
  conf="/tmp/dot1x-peap.conf"
  cat >"$conf" <<EOF
network={
  key_mgmt=WPA-EAP
  eap=PEAP
  identity="${TEST_USER}"
  password="${TEST_PASS}"
  phase2="auth=MSCHAPV2"
  ca_cert="${ca_pem}"
}
EOF
  "${eapol_bin}" -c "$conf" -a "$RADIUS_HOST" -p 1812 -s "$RADIUS_SECRET" -r 1
}

set +e
if docker compose exec -T backend sh -c 'command -v eapol_test >/dev/null 2>&1' 2>/dev/null; then
  echo "Running eapol_test inside the backend container against freeradius:1812 ..."
  run_in_backend | tee /tmp/eapol-test.out
  RC=${PIPESTATUS[0]}
elif command -v eapol_test >/dev/null 2>&1 || command -v eapoltest >/dev/null 2>&1; then
  echo "Running host eapol_test against ${RADIUS_HOST}:1812 ..."
  run_on_host | tee /tmp/eapol-test.out
  RC=${PIPESTATUS[0]}
else
  echo "ERROR: eapol_test not available. Start the stack (make bootstrap) so the" >&2
  echo "backend container can run it, or install eapol_test/eapoltest on this host." >&2
  exit 1
fi
set -e

echo "Fetching recent auth events..."
curl -fsS -H "$AUTH" "$API/events?limit=5" | python3 -m json.tool

# The eapol_test exit code is authoritative (0 only when all rounds succeeded).
if [[ "$RC" -eq 0 ]]; then
  echo "PEAP smoke test completed (see events above)."
  exit 0
fi

echo "eapol_test did not report success (exit=${RC}). Check freeradius logs:"
echo "  docker compose logs freeradius --tail=100"
exit 1
