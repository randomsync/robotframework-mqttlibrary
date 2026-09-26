#!/usr/bin/env sh
# Regenerates mosquitto/passwd_file for the authenticated test broker.
# These are test fixtures only; the passwords are not secrets.
set -eu
cd "$(dirname "$0")/.."
# Keep in step with the image in docker-compose.yml.
IMAGE="${MOSQUITTO_IMAGE:-eclipse-mosquitto:2.1-alpine}"
# Run as the calling user so the file is not left owned by root on Linux.
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/mosquitto:/work" "$IMAGE" sh -c '
  rm -f /work/passwd_file
  touch /work/passwd_file && chmod 0600 /work/passwd_file
  mosquitto_passwd -b /work/passwd_file authuser1 password1
  mosquitto_passwd -b /work/passwd_file authuser2 password2
'
chmod 0644 mosquitto/passwd_file
echo "wrote mosquitto/passwd_file"
