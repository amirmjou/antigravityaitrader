# GCP Hardened Trader Architecture Patterns

## 1. Always-Free Tier Provisioning
Google Cloud offers 1 non-preemptible `e2-micro` instance per month free in `us-central1`, `us-east1`, or `us-west1`:
```bash
gcloud compute instances create trading-bot-server \
    --project="${PROJECT_ID}" \
    --zone=us-central1-a \
    --machine-type=e2-micro \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=20GB \
    --boot-disk-type=pd-standard \
    --tags=tradingbot
```

## 2. Zero-Trust Perimeter Firewall (UFW)
Deny all inbound traffic by default. Only allow incoming SSH (port 22). No open HTTP/webhook ports needed since the bot polls outbound to RPCs and Telegram:
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'SSH Access'
sudo ufw --force enable
```

## 3. Sandboxed Systemd Service (`tradingbot.service`)
Run the bot under an unprivileged system user (`tradingbot`) with strict OS filesystem protection:
```ini
[Unit]
Description=Autonomous Arbitrum Trading Daemon
After=network-online.target

[Service]
Type=simple
User=tradingbot
Group=tradingbot
WorkingDirectory=/opt/tradingbot
ExecStart=/opt/tradingbot/venv/bin/python3 scripts/autonomous_arbitrum_trader.py
Restart=always
RestartSec=5s

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ProtectKernelTunables=true
ProtectControlGroups=true
MemoryDenyWriteExecute=false
EnvironmentFile=/etc/tradingbot/tradingbot.env

[Install]
WantedBy=multi-user.target
```
