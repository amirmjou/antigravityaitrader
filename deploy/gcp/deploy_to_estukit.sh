#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Platform (GCP) One-Click Deployment to Project: estukit.net
# Target: Compute Engine e2-micro (GCP Always-Free Tier)
# ==============================================================================
set -euo pipefail

PROJECT_ID="estukit.net"
ZONE="us-central1-a"
VM_NAME="trading-bot-server"
MACHINE_TYPE="e2-micro"

echo "================================================================================"
echo " DEPLOYING 24/7 ARBITRUM TRADING BOT TO GCP PROJECT: ${PROJECT_ID}"
echo "================================================================================"

# 1. Set Active GCP Project
echo "[1/5] Configuring active project..."
gcloud config set project "${PROJECT_ID}"

# 2. Enable Compute Engine API
echo "[2/5] Ensuring Compute Engine API is enabled..."
gcloud services enable compute.googleapis.com --project="${PROJECT_ID}"

# 3. Create Compute Engine VM Instance if it does not already exist
echo "[3/5] Checking/creating Compute Engine VM instance: ${VM_NAME}..."
if gcloud compute instances describe "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "  -> VM ${VM_NAME} already exists. Skipping creation."
else
    echo "  -> Provisioning Always-Free Tier e2-micro VM in ${ZONE}..."
    gcloud compute instances create "${VM_NAME}" \
        --project="${PROJECT_ID}" \
        --zone="${ZONE}" \
        --machine-type="${MACHINE_TYPE}" \
        --image-family=ubuntu-2204-lts \
        --image-project=ubuntu-os-cloud \
        --boot-disk-size=20GB \
        --boot-disk-type=pd-standard \
        --tags=tradingbot
    echo "  -> VM created successfully."
fi

# 4. Wait for SSH availability
echo "[4/5] Waiting for VM SSH to become ready..."
sleep 15

# 5. Bootstrap VM via gcloud compute ssh
echo "[5/5] Hardening and configuring tradingbot service on ${VM_NAME}..."
gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" --command="
sudo apt-get update && sudo apt-get install -y python3-pip python3-venv git ufw jq
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw --force enable

sudo mkdir -p /opt/tradingbot /etc/tradingbot
if ! id 'tradingbot' &>/dev/null; then
    sudo useradd -r -s /usr/sbin/nologin -d /opt/tradingbot -M tradingbot
fi
sudo chown -R tradingbot:tradingbot /opt/tradingbot
"

echo "================================================================================"
echo " SERVER PROVISIONING COMPLETE ON estukit.net!"
echo "================================================================================"
