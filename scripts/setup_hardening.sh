#!/bin/bash
# UMI Exchange - Host Hardening Script
# OS: Linux Mint / Ubuntu

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Starting UMI Exchange Host Hardening...${NC}"

if [[ "$EUID" -ne 0 ]]; then
  echo -e "${RED}Please run this script with sudo.${NC}"
  exit 1
fi

echo -e "${YELLOW}[1/5] Installing core security packages...${NC}"
apt-get update -y
apt-get install -y ufw fail2ban unattended-upgrades firejail auditd

echo -e "${YELLOW}[2/5] Configuring UFW (Firewall)...${NC}"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
ufw --force enable
echo -e "${GREEN}UFW configured and enabled.${NC}"

echo -e "${YELLOW}[3/5] Configuring fail2ban...${NC}"
systemctl enable fail2ban
systemctl start fail2ban
echo -e "${GREEN}fail2ban enabled.${NC}"

echo -e "${YELLOW}[4/5] Hardening SSH (if installed)...${NC}"
if systemctl is-active --quiet ssh || systemctl is-active --quiet sshd; then
  SSH_CONF="/etc/ssh/sshd_config"
  cp "$SSH_CONF" "${SSH_CONF}.bak"
  
  # Disable root login
  sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$SSH_CONF"
  
  # Check for public keys for standard users before disabling password auth
  USER_KEYS_EXIST=false
  for dir in /home/*/.ssh; do
    if ls "$dir"/authorized_keys 1> /dev/null 2>&1; then
      USER_KEYS_EXIST=true
      break
    fi
  done
  
  if [ "$USER_KEYS_EXIST" = true ] || [ -f /root/.ssh/authorized_keys ]; then
    sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' "$SSH_CONF"
    echo -e "${GREEN}SSH Password Auth disabled (keys found).${NC}"
  else
    echo -e "${YELLOW}Warning: No SSH keys found. Leaving PasswordAuthentication enabled.${NC}"
  fi
  
  systemctl restart ssh || systemctl restart sshd
else
  echo -e "${YELLOW}SSH service not running. Skipping SSH hardening.${NC}"
fi

echo -e "${YELLOW}[5/5] Configuring Auditd rules...${NC}"
AUDIT_RULE_FILE="/etc/audit/rules.d/umi.rules"
cat <<EOF > "$AUDIT_RULE_FILE"
-w /etc/ssh/sshd_config -p wa -k sshd_config
-w /home/umi/umi-exchange/.env -p wa -k env_modifications
EOF
augenrules --load || true
systemctl enable auditd
systemctl restart auditd

echo -e "${GREEN}Hardening complete!${NC}"
