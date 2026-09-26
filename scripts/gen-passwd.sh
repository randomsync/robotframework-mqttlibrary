#!/usr/bin/env sh
# Regenerates mosquitto/passwd_file for the authenticated test broker.
# These are test fixtures only; the passwords are not secrets.
set -eu
cd "$(dirname "$0")/.."
docker run --rm -v "$PWD/mosquitto:/work" eclipse-mosquitto:2 sh -c '
  rm -f /work/passwd_file
  touch /work/passwd_file && chmod 0600 /work/passwd_file
  mosquitto_passwd -b /work/passwd_file authuser1 password1
  mosquitto_passwd -b /work/passwd_file authuser2 password2
'
echo "wrote mosquitto/passwd_file"
