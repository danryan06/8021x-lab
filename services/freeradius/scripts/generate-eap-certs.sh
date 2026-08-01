#!/usr/bin/env bash
# Generate lab EAP server certificates for PEAP (not for production).
set -euo pipefail

CERT_DIR="${1:-/etc/freeradius/3.0/certs}"
mkdir -p "${CERT_DIR}"
cd "${CERT_DIR}"

if [[ -f server.pem && -f server.key && -f ca.pem ]]; then
	echo "EAP lab certificates already present in ${CERT_DIR}"
	exit 0
fi

# Prefer FreeRADIUS bootstrap when available.
if [[ -f bootstrap ]]; then
	bash bootstrap && exit 0
fi

echo "Generating self-signed EAP CA + server cert in ${CERT_DIR}"
openssl genrsa -out ca.key 2048
openssl req -new -x509 -key ca.key -out ca.pem -days 3650 \
	-subj "/C=US/ST=Lab/L=Lab/O=8021X Lab/CN=8021X Lab EAP CA"

openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
	-subj "/C=US/ST=Lab/L=Lab/O=8021X Lab/CN=freeradius.dot1x.lab"
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial \
	-out server.crt -days 825
cat server.crt ca.pem > server.pem
rm -f server.csr
chmod 640 ca.key server.key || true
chmod 644 ca.pem server.pem server.crt || true
echo "Generated EAP lab certificates"
