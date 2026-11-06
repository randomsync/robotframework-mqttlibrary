#!/usr/bin/env sh
# Creates the certificates for the TLS test broker in mosquitto/certs/, which
# is gitignored:
#
#   ca.crt                  the test CA, which signs the two below
#   server.crt, server.key  the broker, for localhost and 127.0.0.1
#   client.crt, client.key  a client, for the mutual TLS listener
#   client-encrypted.key    client.key protected with "client-key-password"
#   other-ca.crt            a CA that signed nothing, for the wrong-CA tests
#
# These are test fixtures only; the keys are not secrets, so every file is
# world-readable and the broker's mosquitto user can read them through the
# bind mount. Does nothing if the certificates exist; pass --force to
# recreate them, then restart the tls broker. The files are written to a
# temporary directory that replaces mosquitto/certs only when all of them
# are made, so a failed run leaves nothing half done.
set -eu
cd "$(dirname "$0")/.."
DIR=mosquitto/certs
# ca.crt, not the directory: docker compose creates an empty one for the bind
# mount if the brokers start first.
if [ -f "$DIR/ca.crt" ] && [ "${1:-}" != "--force" ]; then
  echo "$DIR exists; pass --force to recreate it"
  exit 0
fi
command -v openssl >/dev/null || { echo "openssl is required" >&2; exit 1; }
TMP="$DIR.tmp"
rm -rf "$TMP"
mkdir -p "$TMP"
cd "$TMP"

# The extensions Python's strict verification mode expects, so the
# certificates keep working if a later Python turns it on by default.
cat > extensions.cnf <<'EOF'
[ca]
basicConstraints = critical, CA:TRUE
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash

[server]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:localhost, IP:127.0.0.1
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid

[client]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
EOF

request() { # name common-name
  openssl req -new -newkey rsa:2048 -nodes -keyout "$1.key" -out "$1.csr" \
    -subj "/CN=$2" 2>/dev/null
}

ca() { # name common-name
  request "$1" "$2"
  openssl x509 -req -in "$1.csr" -signkey "$1.key" -out "$1.crt" \
    -days 3650 -sha256 -extfile extensions.cnf -extensions ca 2>/dev/null
}

leaf() { # name common-name extensions
  request "$1" "$2"
  openssl x509 -req -in "$1.csr" -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out "$1.crt" -days 3650 -sha256 -extfile extensions.cnf \
    -extensions "$3" 2>/dev/null
}

ca ca "MQTTLibrary test CA"
ca other-ca "MQTTLibrary other CA"
leaf server localhost server
leaf client robot-client client
openssl rsa -in client.key -aes256 -passout pass:client-key-password \
  -out client-encrypted.key 2>/dev/null

rm -f ./*.csr ./*.srl extensions.cnf ca.key other-ca.key
chmod 0644 ./*
cd ../..
rm -rf "$DIR"
mv "$TMP" "$DIR"
echo "wrote $DIR"
