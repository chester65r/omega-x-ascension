#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
cd "$BACKEND_DIR"
command -v gcloud >/dev/null || { echo "ERROR: run this in Google Cloud Shell." >&2; exit 1; }
command -v python3 >/dev/null || { echo "ERROR: python3 is required." >&2; exit 1; }

PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "ERROR: select the target Google Cloud project in Cloud Shell first." >&2
  exit 1
fi

ZONE="${OMEGA_GCP_ZONE:-me-central2-a}"
REGION="${ZONE%-*}"
VM_NAME="omega-x-ascension"
SA_NAME="omega-runtime"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SECRET_NAME="omega-runtime-env"
ADDRESS_NAME="omega-x-ascension-ip"
WEB_RULE="omega-x-ascension-web"
IAP_RULE="omega-x-ascension-iap-ssh"

printf 'Project: %s\nZone: %s (Dammam, Saudi Arabia by default)\n' "$PROJECT_ID" "$ZONE"
echo "Creates an e2-medium VM, 50 GB persistent disk, reserved IP, Secret Manager secret,"
echo "runtime service account, and firewall rules. These consume trial credit."
echo "This script does not upgrade a Free Trial to paid billing."
echo "An adult account owner should review and run billing-related setup."
read -r -p 'Type CREATE-GCP-VM to proceed: ' CONFIRM
[[ "$CONFIRM" == "CREATE-GCP-VM" ]] || { echo "Cancelled; no resources created."; exit 0; }

# Fail closed if named resources already exist.
if gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "ERROR: VM $VM_NAME already exists in $ZONE." >&2; exit 1
fi
if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "ERROR: secret $SECRET_NAME already exists; refusing to overwrite it." >&2; exit 1
fi
if gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "ERROR: service account $SA_EMAIL already exists." >&2; exit 1
fi
if gcloud compute addresses describe "$ADDRESS_NAME" --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "ERROR: reserved IP $ADDRESS_NAME already exists." >&2; exit 1
fi
for rule in "$WEB_RULE" "$IAP_RULE"; do
  if gcloud compute firewall-rules describe "$rule" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "ERROR: firewall rule $rule already exists." >&2; exit 1
  fi
done

gcloud services enable compute.googleapis.com secretmanager.googleapis.com iam.googleapis.com iap.googleapis.com --project="$PROJECT_ID"

read -r -s -p 'OpenRouter API key (hidden input; do not paste it into chat): ' OPENROUTER_KEY
printf '\n'
if [[ -z "$OPENROUTER_KEY" || "$OPENROUTER_KEY" == *$'\n'* || "$OPENROUTER_KEY" == *$'\r'* ]]; then
  unset OPENROUTER_KEY
  echo "ERROR: a single-line OpenRouter API key is required." >&2
  exit 1
fi
ENV_FILE="$(mktemp "${TMPDIR:-/tmp}/omega-runtime-env.XXXXXX")"
cleanup() { rm -f "$ENV_FILE"; unset OPENROUTER_KEY; }
trap cleanup EXIT

OPENROUTER_KEY="$OPENROUTER_KEY" python3 - "$ENV_FILE" <<'PY'
import os, secrets, sys
from pathlib import Path

p = Path(sys.argv[1])
owner, app, worker, checkpoint, redis = [secrets.token_urlsafe(36) for _ in range(5)]
jwt_secret = secrets.token_urlsafe(48)
sandbox = secrets.token_urlsafe(48)
key = os.environ["OPENROUTER_KEY"]
if "\n" in key or "\r" in key:
    raise SystemExit("OpenRouter key must be a single line.")
lines = [
    "OMEGA_ENV=production",
    f"POSTGRES_PASSWORD={owner}",
    f"OMEGA_APP_PASSWORD={app}",
    f"OMEGA_WORKER_PASSWORD={worker}",
    f"OMEGA_CHECKPOINT_PASSWORD={checkpoint}",
    f"REDIS_PASSWORD={redis}",
    f"OMEGA_MIGRATION_DATABASE_URL=postgresql+psycopg://omega:{owner}@postgres:5432/omega",
    f"OMEGA_DATABASE_URL=postgresql+asyncpg://omega_app:{app}@postgres:5432/omega",
    f"OMEGA_WORKER_DATABASE_URL=postgresql+asyncpg://omega_worker:{worker}@postgres:5432/omega",
    f"OMEGA_CHECKPOINT_DATABASE_URL=postgresql://omega_checkpoint:{checkpoint}@postgres:5432/omega",
    f"OMEGA_REDIS_URL=redis://:{redis}@redis:6379/0",
    f"OMEGA_JWT_SECRET={jwt_secret}",
    f"OMEGA_SANDBOX_TOKEN={sandbox}",
    "OMEGA_SANDBOX_URL=http://sandbox:8090",
    "OMEGA_JWT_ISSUER=omega-x",
    "OMEGA_JWT_AUDIENCE=omega-x-api",
    "OMEGA_JWT_ALGORITHM=HS256",
    "OMEGA_MODEL_PROVIDERS=[]",
    f"OMEGA_OPENROUTER_API_KEY={key}",
    "OMEGA_OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free",
    "OMEGA_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1",
    "OMEGA_OPENROUTER_PRIORITY=100",
    "OMEGA_HF_INFERENCE_MODEL=Qwen/Qwen2.5-1.5B-Instruct:cheapest",
    "OMEGA_HF_INFERENCE_BASE_URL=https://router.huggingface.co/v1",
    "OMEGA_REMOTE_MCP_URL=https://wild-cloud-3h9z2.run.mcp-use.com/mcp",
    "OMEGA_REMOTE_MCP_TIMEOUT_SECONDS=20",
    "OMEGA_ENABLE_COMPUTER_EXECUTION=false",
    "OMEGA_ENABLE_COMPUTER_FILES=true",
    "OMEGA_LOG_LEVEL=INFO",
    "LANGGRAPH_STRICT_MSGPACK=true",
    "OMEGA_NOTIFICATIONS_ENABLED=false",
]
p.write_text("\n".join(lines) + "\n", encoding="utf-8")
p.chmod(0o600)
PY

gcloud secrets create "$SECRET_NAME" --project="$PROJECT_ID" --replication-policy=automatic --data-file="$ENV_FILE"
gcloud iam service-accounts create "$SA_NAME" --project="$PROJECT_ID" --display-name="OMEGA-X runtime"
gcloud secrets add-iam-policy-binding "$SECRET_NAME" --project="$PROJECT_ID" --member="serviceAccount:${SA_EMAIL}" --role="roles/secretmanager.secretAccessor"

gcloud compute firewall-rules create "$WEB_RULE" --project="$PROJECT_ID" --network=default --direction=INGRESS --action=ALLOW --allow=tcp:80,tcp:443 --source-ranges=0.0.0.0/0 --target-tags=omega-x-gcp
gcloud compute firewall-rules create "$IAP_RULE" --project="$PROJECT_ID" --network=default --direction=INGRESS --action=ALLOW --allow=tcp:22 --source-ranges=35.235.240.0/20 --target-tags=omega-x-gcp

gcloud compute addresses create "$ADDRESS_NAME" --project="$PROJECT_ID" --region="$REGION" --network-tier=PREMIUM
STATIC_IP="$(gcloud compute addresses describe "$ADDRESS_NAME" --project="$PROJECT_ID" --region="$REGION" --format='value(address)')"

gcloud compute instances create "$VM_NAME" --project="$PROJECT_ID" --zone="$ZONE" --machine-type=e2-medium --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud --boot-disk-size=50GB --boot-disk-type=pd-balanced --address="$STATIC_IP" --network=default --tags=omega-x-gcp --service-account="$SA_EMAIL" --scopes=https://www.googleapis.com/auth/cloud-platform --metadata="omega-env-secret=$SECRET_NAME" --metadata-from-file="startup-script=$SCRIPT_DIR/startup.sh"

echo
echo "VM creation requested; the first boot can take several minutes."
echo "Reserved IP: $STATIC_IP"
echo "Temporary HTTPS URL (once Caddy gets its certificate): https://${STATIC_IP}.sslip.io"
echo "Keep Railway unchanged until real model inference and workflow tests pass."
echo "Startup logs: gcloud compute ssh $VM_NAME --zone=$ZONE --tunnel-through-iap --command='sudo tail -n 200 /var/log/omega-bootstrap.log'"
