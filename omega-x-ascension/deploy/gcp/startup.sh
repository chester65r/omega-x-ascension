#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
exec > >(tee -a /var/log/omega-bootstrap.log /dev/console) 2>&1

log() { printf '[OMEGA-GCP] %s\n' "$*"; }
trap 'status=$?; log "STARTUP FAILED (exit ${status}); inspect /var/log/omega-bootstrap.log"; exit "$status"' ERR

META="http://metadata.google.internal/computeMetadata/v1"
meta() { curl --fail --silent --show-error --retry 5 -H 'Metadata-Flavor: Google' "${META}/$1"; }

PROJECT_ID="$(meta project/project-id)"
SECRET_NAME="$(meta instance/attributes/omega-env-secret)"
[[ -n "$PROJECT_ID" && -n "$SECRET_NAME" ]] || { log "Missing project or secret metadata."; exit 1; }

log "Installing Docker, Compose, and Caddy."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git gnupg docker.io docker-compose-v2 debian-keyring debian-archive-keyring apt-transport-https

curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
apt-get update
apt-get install -y caddy
systemctl enable --now docker

log "Retrieving protected runtime environment from Secret Manager."
ACCESS_TOKEN="$(meta instance/service-accounts/default/token | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
install -d -m 0700 /opt/omega
curl --fail --silent --show-error --retry 12 --retry-all-errors --retry-delay 5 \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets/${SECRET_NAME}/versions/latest:access" \
  | python3 -c 'import base64,json,sys; sys.stdout.write(base64.b64decode(json.load(sys.stdin)["payload"]["data"]).decode("utf-8"))' \
  > /opt/omega/runtime.env
unset ACCESS_TOKEN
chmod 0600 /opt/omega/runtime.env

log "Downloading current OMEGA-X application source."
if [[ ! -d /opt/omega/repo/.git ]]; then
  git clone --depth 1 https://github.com/chester65r/omega-x-ascension.git /opt/omega/repo
fi
BACKEND_DIR="/opt/omega/repo/omega-x-ascension"
[[ -f "${BACKEND_DIR}/docker-compose.yml" ]] || { log "Repository layout check failed."; exit 1; }
install -m 0600 /opt/omega/runtime.env "${BACKEND_DIR}/.env"
cd "$BACKEND_DIR"

log "Building containers sequentially to reduce memory pressure."
docker compose build --parallel 1
log "Starting API, worker, PostgreSQL, Redis, migrations, and isolated sandbox."
docker compose up -d

PUBLIC_IP="$(meta instance/network-interfaces/0/access-configs/0/external-ip)"
PUBLIC_HOST="${PUBLIC_IP}.sslip.io"
log "Configuring HTTPS reverse proxy for ${PUBLIC_HOST}."
cat > /etc/caddy/Caddyfile <<EOF
${PUBLIC_HOST} {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000
}
EOF
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl enable caddy
systemctl restart caddy

log "Waiting for API liveness."
READY=0
for attempt in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:8000/health/live >/dev/null; then
    READY=1
    break
  fi
  sleep 5
done
if [[ "$READY" != "1" ]]; then
  docker compose ps || true
  docker compose logs --tail=100 api worker migrate sandbox || true
  log "API liveness failed; inspect service logs before retrying."
  exit 1
fi

log "Checking readiness endpoint (database, queue, and provider configuration)."
curl --fail --silent --show-error http://127.0.0.1:8000/health/ready || true
log "Checking model listing health; this does not prove completion generation."
curl --fail --silent --show-error http://127.0.0.1:8000/health/models || true

log "Running one small real model-completion smoke test. Free-model availability/rate limits may cause it to fail."
set +e
docker compose exec -T api python scripts/verify_model_provider.py
MODEL_STATUS=$?
set -e
if [[ "$MODEL_STATUS" == "0" ]]; then
  log "LIVE_MODEL_INFERENCE=PASS"
else
  log "LIVE_MODEL_INFERENCE=NOT_VERIFIED (provider, quota, model availability, or network may need review)"
fi

log "Deployment boot script finished."
log "Temporary API URL: https://${PUBLIC_HOST}"
log "Check certificate issuance and test authenticated workflows before changing the Android app."
