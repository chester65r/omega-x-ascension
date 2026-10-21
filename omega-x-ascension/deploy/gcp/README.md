# OMEGA-X on Google Cloud (trial migration)

This is a staging migration path from Railway to one Compute Engine VM. It deliberately leaves Railway untouched. Do not switch the Android app or delete Railway until health checks, an actual model completion, authenticated workflow tests, and database checks pass.

## What the bootstrap creates

- One Ubuntu 24.04 Compute Engine e2-medium VM in me-central2-a (Dammam, Saudi Arabia by default), with a 50 GB balanced persistent boot disk.
- Docker Compose runs the existing API, worker, PostgreSQL/pgvector, Redis, migrations, and separate network-isolated sandbox.
- A reserved external IPv4 address and a temporary HTTPS hostname using sslip.io; Caddy requests and renews the TLS certificate.
- A Secret Manager secret containing generated database/Redis/JWT/sandbox values and the OpenRouter key entered interactively in Cloud Shell.
- A runtime service account granted access only to that one Secret Manager secret.
- Public firewall ingress only for HTTP/HTTPS. SSH is restricted to Google's IAP TCP forwarding range.

Computer shell execution remains disabled (OMEGA_ENABLE_COMPUTER_EXECUTION=false). Keep it disabled for public access until the sandbox uses stronger per-job isolation. The file workspace feature remains enabled. The OpenRouter free model can be rate-limited or unavailable; the inference smoke test can fail even if the VM itself deployed.

## Requirements and cost guardrails

1. A Google Cloud project with the Free Trial billing account already set up and Compute Engine/Secret Manager APIs available. The script does not enable or upgrade paid billing and does not handle payment verification.
2. An adult account owner should complete any payment/identity verification and review resource creation, particularly if a payment method is attached.
3. The script requests an e2-medium VM, a persistent disk, a reserved IP, firewall rules, and a Secret Manager entry. These consume trial credit. Google currently advertises $300 credit for 90 days; resources are stopped when the Free Trial account closes unless the account is upgraded. Do not upgrade simply to keep this test running without reviewing charges and obtaining the account owner's approval.
4. A standard budget alert is not a hard cap: it sends notices but does not automatically stop usage. Review Google's spend-cap feature if eligible, and leave the account on Free Trial unless a responsible account owner decides otherwise.
5. The temporary sslip.io hostname is for migration testing only. A custom domain is recommended before treating this as a long-term public endpoint.
6. PostgreSQL and Redis are not exposed publicly. The VM needs ongoing updates, backups, and monitoring. No claim of production readiness should be made until these are configured and tested.

Official references:
- Free Trial: https://cloud.google.com/signup-faqs
- Compute Engine VM creation: https://docs.cloud.google.com/compute/docs/instances/create-start-instance
- Startup scripts: https://docs.cloud.google.com/compute/docs/instances/startup-scripts/linux
- Secret Manager: https://docs.cloud.google.com/secret-manager/docs
- Billing budget alerts and spend caps: https://docs.cloud.google.com/billing/docs/how-to/budgets

## Run from Google Cloud Shell

Open Cloud Shell from the selected Google Cloud project, clone this repository and branch, and enter the backend directory:

    git clone --branch gcp-migration-prep https://github.com/chester65r/omega-x-ascension.git
    cd omega-x-ascension/omega-x-ascension
    bash deploy/gcp/bootstrap.sh

The script checks for conflicts with its named resources and asks for the exact confirmation string CREATE-GCP-VM. The OpenRouter API key is collected with hidden terminal input and stored server-side in Secret Manager; it is not committed to GitHub or printed. Never paste a key, JWT, password, payment data, or service-account key into chat.

The default zone is me-central2-a. To use another E2-capable zone, set OMEGA_GCP_ZONE before running the script, for example:

    export OMEGA_GCP_ZONE=me-central2-b

## Verification and rollback

- Check the VM status and startup log from Cloud Shell:

    gcloud compute instances describe omega-x-ascension --zone=me-central2-a --format='get(status)'
    gcloud compute ssh omega-x-ascension --zone=me-central2-a --tunnel-through-iap --command='sudo tail -n 200 /var/log/omega-bootstrap.log'

- Test these routes on the temporary HTTPS host: /health/live, /health/ready, /health/models, and /version.
- Test actual chat completion and a short low-risk workflow from Android after a short-lived JWT is created securely on the server. /health/models alone is not proof of generated text.
- Check Docker service status/logs over IAP SSH using: docker compose ps and docker compose logs --tail=150 api worker migrate sandbox, from the backend directory on the VM.
- Before cutover, update the app endpoint and auth configuration through the repository's intended setup, then test the APK against the new host.
- To roll back, point the app back to the current Railway API. Keep Railway and its data unchanged during the test.
- Do not delete the new VM until any data that matters has been backed up. To stop consuming compute credit if a test is abandoned, stop or delete the VM and separately review/delete the reserved IP, firewall rules, service account, and Secret Manager secret/version. Deleting the VM alone does not remove those separate resources or guarantee database backups.
