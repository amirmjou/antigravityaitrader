# GCP Hardening Verification Checklist

Before leaving the bot to run 24/7 in production:

1. **Firewall Verification**:
   ```bash
   sudo ufw status verbose
   ```
   Must display: `Status: active`, `Default: deny (incoming), allow (outgoing)`. Only port 22/tcp should be allowed.

2. **Secret File Permissions**:
   ```bash
   ls -la /etc/tradingbot/tradingbot.env
   ```
   Must display `-rw-r-----` (0640 or 0600) owned by `root:tradingbot`.

3. **Systemd Recovery Test**:
   ```bash
   sudo pkill -9 -f autonomous_arbitrum_trader.py
   sleep 7
   sudo systemctl status tradingbot
   ```
   Must automatically return to `active (running)` state.

4. **Boot Persistence**:
   ```bash
   sudo systemctl is-enabled tradingbot
   ```
   Must return `enabled`.
