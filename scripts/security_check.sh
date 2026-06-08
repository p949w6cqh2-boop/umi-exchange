#!/bin/bash
# UMI Exchange - Daily Security Check

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "[${GREEN}PASS${NC}] $1"; }
fail() { echo -e "[${RED}FAIL${NC}] $1"; echo -e "       ${YELLOW}Fix: $2${NC}"; }
warn() { echo -e "[${YELLOW}WARN${NC}] $1"; echo -e "       $2"; }

echo "=== UMI Daily Security Check ==="

# 1. UFW Check
if command -v ufw >/dev/null 2>&1; then
    if sudo ufw status | grep -q "Status: active"; then
        pass "UFW is active."
    else
        fail "UFW is inactive." "Run: sudo ufw enable"
    fi
else
    fail "UFW not installed." "Run: sudo apt install ufw"
fi

# 2. fail2ban Check
if systemctl is-active --quiet fail2ban; then
    pass "fail2ban is running."
else
    fail "fail2ban is not running." "Run: sudo systemctl start fail2ban"
fi

# 3. Firejail Check
if command -v firejail >/dev/null 2>&1; then
    pass "firejail is installed."
else
    fail "firejail is not installed." "Run: sudo apt install firejail"
fi

# 4. Secret Scanning (ggshield)
if command -v ggshield >/dev/null 2>&1; then
    if ggshield secret scan repo . > /dev/null 2>&1; then
        pass "No secrets found in recent git history."
    else
        fail "Secrets detected by ggshield." "Review git history and rotate exposed credentials."
    fi
else
    warn "ggshield is not installed." "Install ggshield for automated secret scanning: pip install ggshield"
fi

# 5. Antigravity IDE
echo ""
echo -e "${YELLOW}Manual Check Required: Antigravity IDE Approval Settings${NC}"
echo "Have you verified that your Antigravity IDE has approval thresholds set to MANUAL for:"
echo "  - Terminal Commands?"
echo "  - File Modifications?"
read -p "Type 'y' if verified: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    pass "Antigravity IDE permissions verified."
else
    fail "Antigravity IDE permissions unverified." "Update your Antigravity settings immediately."
fi

echo "Security check complete."
