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

# 5. X-Real-IP spoof-resistance (rate-limit / audit IP-trust foundation)
# The app trusts X-Real-IP for per-IP rate-limiting AND salted audit-log IP
# hashing. That is ONLY safe if the edge proxy (Caddy) overwrites the header so
# a client cannot forge it. This class is not unit-testable in isolation — it
# depends on live proxy config — so we assert it black-box against the running
# site: fire more login POSTs than the per-IP limit, each carrying a DIFFERENT
# forged X-Real-IP. If the forgery were trusted, every request would land in its
# own bucket and NONE would be throttled; correct config collapses them onto the
# one real connecting IP, so at least one 429 must appear.
TARGET_URL="${1:-${SITE_URL:-https://localhost}}"
LOGIN_URL="${TARGET_URL%/}/auth/login/"
if curl -sk -o /dev/null --max-time 5 "$TARGET_URL" 2>/dev/null; then
    spoof_429=0
    for i in $(seq 1 8); do
        code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 5 \
            -X POST "$LOGIN_URL" \
            -H "X-Real-IP: 203.0.113.$i" \
            --data "login=probe-$i&password=wrong" 2>/dev/null || echo "000")
        [ "$code" = "429" ] && spoof_429=$((spoof_429 + 1))
    done
    if [ "$spoof_429" -gt 0 ]; then
        pass "X-Real-IP spoofing does not bypass rate limiting ($spoof_429/8 rotated-IP requests throttled)."
    else
        fail "X-Real-IP appears client-spoofable — 8 forged-IP login POSTs, zero throttled." \
             "Confirm Caddy sets 'header_up X-Real-IP {remote_host}' (docker/Caddyfile.prod) and RATELIMIT is enabled. A client-trusted X-Real-IP defeats login throttles and forges audit-log source IPs."
    fi
else
    warn "Skipped X-Real-IP spoof check — $TARGET_URL unreachable." "Run against the live host: bash scripts/security_check.sh https://your-domain"
fi

# 6. Antigravity IDE
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
