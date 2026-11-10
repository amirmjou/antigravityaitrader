#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Shell Standalone Deployment for antigravityaitrader
# ==============================================================================
set -euo pipefail

PROJECT_ID="antigravityaitrader"
ZONE="us-central1-a"
VM_NAME="trading-bot-server"

echo "=== [1/3] Setting project & enabling Compute Engine ==="
gcloud config set project "${PROJECT_ID}"
gcloud services enable compute.googleapis.com --project="${PROJECT_ID}"

echo "=== [2/3] Provisioning e2-micro VM (${VM_NAME}) ==="
if gcloud compute instances describe "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "VM ${VM_NAME} already exists."
else
    gcloud compute instances create "${VM_NAME}" \
        --project="${PROJECT_ID}" \
        --zone="${ZONE}" \
        --machine-type=e2-micro \
        --image-family=ubuntu-2204-lts \
        --image-project=ubuntu-os-cloud \
        --boot-disk-size=20GB \
        --boot-disk-type=pd-standard \
        --tags=tradingbot
fi

echo "=== [3/3] Ready! Connecting to VM ==="
echo "Run this command to SSH into your VM:"
echo "gcloud compute ssh ${VM_NAME} --zone=${ZONE} --project=${PROJECT_ID}"
