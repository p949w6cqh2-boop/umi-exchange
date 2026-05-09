#!/bin/bash
# UMI Self-Hosting Security Hardening Script
# Idempotent: safe to run multiple times.
# Tested on: Ubuntu 22.04 LTS, Ubuntu 24.04 LTS
# Run as root: sudo bash scripts/harden.sh
set -euo pipefail
echo "=== UMI VPS Hardening ==="

# 1. System updates + unattended-upgrades
echo "[1/6] Configuring automatic security updates..."
apt-get update -qq
apt-get install -y -qq unattended-upgrades apt-listchanges
dpkg-reconfigure -plow unattended-upgrades
sed -i 's|//Unattended-Upgrade::Automatic-Reboot "false"|Unattended-Upgrade::Automatic-Reboot "true"|' /etc/apt/apt.conf.d/50unattended-upgrades
sed -i 's|//Unattended-Upgrade::Automatic-Reboot-Time "02:00"|Unattended-Upgrade::Automatic-Reboot-Time "02:00"|' /etc/apt/apt.conf.d/50unattended-upgrades

# 2. Firewall (UFW)
echo "[2/6] Configuring firewall..."
apt-get install -y -qq ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
ufw --force enable

# 3. Fail2ban for SSH brute-force protection
echo "[3/6] Installing fail2ban..."
apt-get install -y -qq fail2ban
cat > /etc/fail2ban/jail.local << 'JAILEOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 5
bantime = 3600
findtime = 600
JAILEOF
systemctl restart fail2ban

# 4. SSH hardening
echo "[4/6] Hardening SSH..."
if [ -f /root/.ssh/authorized_keys ] && [ -s /root/.ssh/authorized_keys ]; then
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i 's/#PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
    systemctl restart sshd
    echo "  SSH password auth disabled (public key detected)."
else
    echo "  WARNING: No SSH key found. Password auth remains enabled."
    echo "  Add a public key to /root/.ssh/authorized_keys, then re-run."
fi

# 5. Logwatch for daily summaries
echo "[5/6] Installing logwatch..."
apt-get install -y -qq logwatch
mkdir -p /etc/logwatch/conf
cat > /etc/logwatch/conf/logwatch.conf << 'LWEOF'
Output = file
Filename = /var/log/logwatch-daily.txt
Detail = Med
Range = yesterday
LWEOF

# 6. Kernel security parameters
echo "[6/6] Applying kernel security parameters..."
sysctl -w net.ipv4.conf.all.accept_source_route=0 >/dev/null 2>&1
sysctl -w net.ipv4.conf.all.accept_redirects=0 >/dev/null 2>&1
sysctl -w net.ipv4.conf.all.log_martians=1 >/dev/null 2>&1

echo ""
echo "=== Hardening complete ==="
echo "Firewall: SSH + HTTP + HTTPS only"
echo "Fail2ban: SSH brute-force protection active"
echo "Auto-updates: Security patches applied automatically"
echo "Logwatch: Daily summary at /var/log/logwatch-daily.txt"
echo ""
echo "NEXT STEPS:"
echo "1. Verify SSH access works before closing this session."
echo "2. Run: docker compose up -d (to start the application)."
echo "3. Set up off-site backups (see scripts/backup.sh)."
