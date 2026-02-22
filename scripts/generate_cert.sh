#!/bin/bash
#
# Generate a self-signed TLS certificate for local HTTPS development.
# Run this once during setup. Outputs cert.pem and key.pem in the project root.
#
# Usage:
#   bash scripts/generate_cert.sh
#   bash scripts/generate_cert.sh --days 3650   # 10-year cert
#

set -e

DAYS=825   # Max accepted by most browsers without complaint
CERT_DIR="$(dirname "$0")/.."
CERT_FILE="$CERT_DIR/cert.pem"
KEY_FILE="$CERT_DIR/key.pem"

# Parse optional --days flag
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --days) DAYS="$2"; shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
    shift
done

echo "Generating self-signed certificate (${DAYS} days)..."

openssl req -x509 -newkey rsa:4096 -sha256 -nodes \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -days "$DAYS" \
    -subj "/CN=orchard-ui" \
    -addext "subjectAltName=IP:127.0.0.1,DNS:localhost"

chmod 600 "$KEY_FILE"

echo ""
echo "Certificate : $CERT_FILE"
echo "Private key : $KEY_FILE"
echo ""
echo "To trust this cert in your browser:"
echo "  macOS:  open '$CERT_FILE' → Keychain Access → double-click → Trust → Always Trust"
echo "  Linux:  sudo cp '$CERT_FILE' /usr/local/share/ca-certificates/orchard-ui.crt && sudo update-ca-certificates"
echo ""
echo "Add to .env:"
echo "  SSL_CERT=cert.pem"
echo "  SSL_KEY=key.pem"
