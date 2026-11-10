#!/usr/bin/env bash
# Automated Google Cloud Run + Secret Manager Provisioning & Deployment Script (Bash)
# Usage:
#   ./deploy/deploy_gcp.sh <PROJECT_ID> [REGION] [ALLOWED_ORIGINS]

set -euo pipefail

PROJECT_ID="${1:-}"
REGION="${2:-us-central1}"
ALLOWED_ORIGINS="${3:-http://localhost:3000,http://127.0.0.1:3000}"
SERVICE_NAME="agentic-trading-bot"
REPO_NAME="trading-repo"
SA_NAME="agentic-trading-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if [[ -z "$PROJECT_ID" ]]; then
  echo "Usage: $0 <GCP_PROJECT_ID> [REGION] [ALLOWED_ORIGINS]"
  exit 1
fi

echo "================================================================"
echo " AGENTIC TRADING BOT - GOOGLE CLOUD HARDENED DEPLOYMENT"
echo "================================================================"
echo "Project ID:   ${PROJECT_ID}"
echo "Region:       ${REGION}"
echo "Service Name: ${SERVICE_NAME}"

gcloud config set project "${PROJECT_ID}"

echo "[1/6] Enabling Google Cloud APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com

echo "[2/6] Configuring Least-Privilege Service Account (${SA_EMAIL})..."
if ! gcloud iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Agentic Trading Bot Runtime Service Account"
fi

echo "[3/6] Ensuring Artifact Registry Repository '${REPO_NAME}'..."
if ! gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Hardened Agentic Trading Bot Container Repository"
fi

echo "[4/6] Provisioning TRADING_API_KEY in Google Secret Manager..."
if ! gcloud secrets describe TRADING_API_KEY >/dev/null 2>&1; then
  gcloud secrets create TRADING_API_KEY --replication-policy="automatic"
  openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add TRADING_API_KEY --data-file=-
  echo "Created new 256-bit TRADING_API_KEY in Secret Manager."
else
  echo "TRADING_API_KEY already exists in Secret Manager (reusing latest version)."
fi

gcloud secrets add-iam-policy-binding TRADING_API_KEY \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" >/dev/null

echo "[5/6] Submitting hardened build & deploying to Cloud Run..."
gcloud builds submit --config cloudbuild.yaml \
  --substitutions="_REGION=${REGION},_REPO_NAME=${REPO_NAME},_SERVICE_NAME=${SERVICE_NAME},_SERVICE_ACCOUNT=${SA_EMAIL},_ALLOWED_ORIGINS=${ALLOWED_ORIGINS}"

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --format='value(status.url)')"
echo "================================================================"
echo " [6/6] DEPLOYMENT COMPLETE!"
echo "================================================================"
echo "Cloud Run URL: ${SERVICE_URL}"
echo "Health Check:  ${SERVICE_URL}/api/health"
echo ""
echo "Test authenticated access:"
echo "  TOKEN=\$(gcloud secrets versions access latest --secret=TRADING_API_KEY)"
echo "  curl -H \"Authorization: Bearer \${TOKEN}\" \"${SERVICE_URL}/api/performance/200-trades\""
