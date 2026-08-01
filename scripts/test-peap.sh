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

echo "Creating RADIUS client (lab documentation / NAS sync)..."
curl -fsS -X POST "$API/clients" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"lab_id\":\"${LAB_ID}\",\"name\":\"peap-test-nas\",\"ip_address\":\"10.255.255.1\",\"shared_secret\":\"nas-secret\",\"device_type\":\"test\",\"enabled\":true}" \
  >/dev/null || true

echo "Creating PEAP test user ${TEST_USER}..."
curl -fsS -X POST "$API/users" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"lab_id\":\"${LAB_ID}\",\"username\":\"${TEST_USER}\",\"password\":\"${TEST_PASS}\",\"groups\":[\"lab\"],\"status\":\"active\"}" \
  >/dev/null

CA_PEM="/tmp/dot1x-ca.pem"
docker compose cp freeradius:/etc/freeradius/3.0/certs/ca.pem "$CA_PEM" 2>/dev/null \
  || docker compose exec -T freeradius cat /etc/freeradius/3.0/certs/ca.pem >"$CA_PEM"

CONF="/tmp/dot1x-peap.conf"
cat >"$CONF" <<EOF
network={
  key_mgmt=WPA-EAP
  eap=PEAP
  identity="${TEST_USER}"
  password="${TEST_PASS}"
  phase2="auth=MSCHAPV2"
  ca_cert="${CA_PEM}"
}
EOF

if ! command -v eapol_test >/dev/null 2>&1 && ! command -v eapoltest >/dev/null 2>&1; then
  echo "Installing eapoltest..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq eapoltest
fi

EAPOL_BIN="$(command -v eapol_test || command -v eapoltest)"
echo "Running ${EAPOL_BIN} against ${RADIUS_HOST}:1812 ..."
set +e
"${EAPOL_BIN}" -c "$CONF" -a "$RADIUS_HOST" -p 1812 -s "$RADIUS_SECRET" -r 1 | tee /tmp/eapol-test.out
RC=${PIPESTATUS[0]}
set -e

echo "Fetching recent auth events..."
curl -fsS -H "$AUTH" "$API/events?limit=5" | python3 -m json.tool

if grep -q "SUCCESS" /tmp/eapol-test.out || [[ "$RC" -eq 0 ]]; then
  echo "PEAP smoke test completed (see events above)."
  exit 0
fi

echo "eapol_test did not report success (exit=${RC}). Check freeradius logs:"
echo "  docker compose logs freeradius --tail=100"
exit 1
