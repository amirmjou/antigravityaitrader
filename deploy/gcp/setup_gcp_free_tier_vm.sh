#!/usr/bin/env bash
# ==============================================================================
# Google Cloud Platform (GCP) 24/7 Hardened Server Setup Script
# Target: Compute Engine e2-micro (Eligible for GCP Always-Free Tier)
# ==============================================================================
set -euo pipefail

echo "================================================================================"
echo " PROVISIONING HARDENED ARBITRUM TRADING BOT ON GOOGLE CLOUD"
echo "================================================================================"

# 1. Update OS and install essential runtime packages
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y python3-pip python3-venv git ufw fail2ban jq

# 2. Configure Host Network Firewall (UFW)
# Default Deny Incoming, Allow Outgoing, Allow SSH
echo "[*] Hardening network perimeter (UFW)..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'SSH Access'
sudo ufw --force enable

# 3. Create dedicated system user for isolation
echo "[*] Creating isolated system user 'tradingbot'..."
if ! id "tradingbot" &>/dev/null; then
    sudo useradd -r -s /usr/sbin/nologin -d /opt/tradingbot -M tradingbot
fi

# 4. Set up application directory
sudo mkdir -p /opt/tradingbot
sudo mkdir -p /etc/tradingbot
sudo cp -r . /opt/tradingbot/
sudo chown -R tradingbot:tradingbot /opt/tradingbot

# 5. Secure environment secrets
# Secrets are loaded into /etc/tradingbot/tradingbot.env with 0600 permissions
echo "[*] Setting up secret management..."
sudo cp .env /etc/tradingbot/tradingbot.env 2>/dev/null || true
# Ensure proper ownership and permissions
sudo chown root:tradingbot /etc/tradingbot/tradingbot.env
sudo chmod 640 /etc/tradingbot/tradingbot.env

# 6. Install Python dependencies
echo "[*] Installing Python packages in virtualenv..."
sudo python3 -m venv /opt/tradingbot/venv
sudo /opt/tradingbot/venv/bin/pip install --upgrade pip
if [ -f "/opt/tradingbot/deploy/gcp/requirements_bot.txt" ]; then
    sudo /opt/tradingbot/venv/bin/pip install -r /opt/tradingbot/deploy/gcp/requirements_bot.txt
elif [ -f "/opt/tradingbot/requirements.txt" ]; then
    sudo /opt/tradingbot/venv/bin/pip install -r /opt/tradingbot/requirements.txt
fi
sudo chown -R tradingbot:tradingbot /opt/tradingbot/venv

# 7. Configure and enable Systemd hardened service
echo "[*] Installing systemd hardened service..."
sudo cp /opt/tradingbot/deploy/gcp/tradingbot.service /etc/systemd/system/tradingbot.service
# Update ExecStart to use virtualenv python
sudo sed -i 's|/usr/bin/python3|/opt/tradingbot/venv/bin/python3|g' /etc/systemd/system/tradingbot.service

sudo systemctl daemon-reload
sudo systemctl enable tradingbot.service
sudo systemctl restart tradingbot.service

echo "================================================================================"
echo " GOOGLE CLOUD HARDENED DEPLOYMENT COMPLETE!"
echo "================================================================================"
echo " Service Status:  sudo systemctl status tradingbot"
echo " Live Logs:       sudo journalctl -u tradingbot -f"
echo " Reboot Survival: Enabled (24/7 automatic recovery on failure or reboot)"
echo "================================================================================"
