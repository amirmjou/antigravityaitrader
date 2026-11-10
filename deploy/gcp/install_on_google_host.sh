#!/usr/bin/env bash
# ==============================================================================
# Antigravity Arbitrum Trader — Turnkey Installation for New Google Host
# Repository: https://github.com/amirmjou/antigravityaitrader.git
# ==============================================================================
set -euo pipefail

echo "================================================================================"
echo " PROVISIONING ANTIGRAVITY TRADING BOT ON GOOGLE HOST"
echo "================================================================================"

# 1. Update OS and install prerequisites
echo "[1/6] Updating system and installing base dependencies..."
sudo apt-get update && sudo apt-get install -y python3-pip python3-venv git ufw fail2ban jq

# 2. Configure Host Network Firewall (UFW)
echo "[2/6] Enforcing zero-trust network firewall (UFW)..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'SSH Access'
sudo ufw --force enable

# 3. Create dedicated system user
echo "[3/6] Creating isolated system user 'tradingbot'..."
if ! id "tradingbot" &>/dev/null; then
    sudo useradd -r -s /usr/sbin/nologin -d /opt/tradingbot -M tradingbot
fi

# 4. Clone or update repository
echo "[4/6] Setting up application in /opt/tradingbot..."
sudo mkdir -p /opt/tradingbot /etc/tradingbot
if [ -d "/opt/tradingbot/.git" ]; then
    echo "  -> Repository exists. Pulling latest main..."
    sudo git -C /opt/tradingbot pull origin main
else
    echo "  -> Cloning repository from GitHub..."
    sudo git clone https://github.com/amirmjou/antigravityaitrader.git /opt/tradingbot
fi
sudo chown -R tradingbot:tradingbot /opt/tradingbot

# 5. Build Python Virtual Environment
echo "[5/6] Building hardened Python virtualenv..."
sudo python3 -m venv /opt/tradingbot/venv
sudo /opt/tradingbot/venv/bin/pip install --upgrade pip
if [ -f "/opt/tradingbot/deploy/gcp/requirements_bot.txt" ]; then
    sudo /opt/tradingbot/venv/bin/pip install -r /opt/tradingbot/deploy/gcp/requirements_bot.txt
else
    sudo /opt/tradingbot/venv/bin/pip install -r /opt/tradingbot/requirements.txt
fi
sudo chown -R tradingbot:tradingbot /opt/tradingbot/venv

# 6. Configure Systemd Service
echo "[6/6] Installing hardened systemd service..."
sudo cp /opt/tradingbot/deploy/gcp/tradingbot.service /etc/systemd/system/tradingbot.service
sudo sed -i 's|/usr/bin/python3|/opt/tradingbot/venv/bin/python3|g' /etc/systemd/system/tradingbot.service

# If .env does not exist in /etc/tradingbot, create a template
if [ ! -f "/etc/tradingbot/tradingbot.env" ]; then
    echo "[!] /etc/tradingbot/tradingbot.env not found. Initializing from template..."
    sudo cp /opt/tradingbot/.env.example /etc/tradingbot/tradingbot.env
    sudo chmod 600 /etc/tradingbot/tradingbot.env
    echo "================================================================================"
    echo " IMPORTANT: Please edit /etc/tradingbot/tradingbot.env with your real keys:"
    echo " sudo nano /etc/tradingbot/tradingbot.env"
    echo "================================================================================"
fi

sudo systemctl daemon-reload
sudo systemctl enable tradingbot.service

echo "================================================================================"
echo " INSTALLATION COMPLETE ON GOOGLE HOST!"
echo "================================================================================"
echo " Next Steps:"
echo " 1. Put your credentials in /etc/tradingbot/tradingbot.env"
echo " 2. Start bot:   sudo systemctl start tradingbot"
echo " 3. View status: sudo systemctl status tradingbot"
echo " 4. View logs:   sudo journalctl -u tradingbot -f"
echo "================================================================================"
