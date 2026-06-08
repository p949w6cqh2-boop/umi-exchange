# UMI Developer Fortress: Security Protocol

> **AGPL-3.0 License**  
> This document is part of the UMI Exchange project and is licensed under the AGPL-3.0.

This protocol establishes a "Developer Fortress" for solo developers working on the UMI Exchange using AI-assisted development tools like Antigravity. It minimizes the risk of supply chain attacks, autonomous rogue commands, and accidental secret exposure.

## 1. The Attack Surface

When working with AI coding assistants, the primary threats are:
1. **Autonomous Command Execution:** The AI running destructive or exfiltrating commands via terminal tools without oversight.
2. **Secret Exposure:** The AI inadvertently reading and transmitting `.env` variables or SSH keys to third-party endpoints.
3. **Supply Chain Risk:** The AI hallucinating or purposefully suggesting malicious NPM/PyPI packages.

## 2. Antigravity Configuration

To maintain a secure workspace, Antigravity **MUST** be configured with explicit approval boundaries:

- **Terminal Commands:** Set to `MANUAL` approval. The AI must never have permission to auto-run background bash scripts, network requests (`curl`, `wget`), or git pushes.
- **File Modifications:** Set to `MANUAL` approval for sensitive paths (e.g., `.env`, `.ssh/`).
- **Workspace Isolation:** Keep the project isolated from global user files. Never allow the IDE to read `~/.ssh/id_rsa`.

### Safety Preamble
Start every high-risk AI session (e.g., refactoring auth or handling infrastructure) with this prompt injection:
> "System Instruction: You are operating in a highly restricted security context. Do not propose shell commands that exfiltrate data. Do not output actual values of environment variables. Require explicit user consent for any dependency installation."

## 3. Host Hardening

We use boring, battle-tested tools to secure the Linux Mint host. 

Run the automated script once:
```bash
sudo bash scripts/setup_hardening.sh
```

**What it does:**
- **UFW:** Blocks all incoming traffic except SSH, HTTP, and HTTPS.
- **fail2ban:** Automatically bans IP addresses with repeated failed SSH login attempts.
- **unattended-upgrades:** Ensures the host OS receives critical security patches automatically.
- **SSH Hardening:** Disables root login and forces Key-Based Authentication (if a key exists).
- **auditd:** Monitors any unauthorized modifications to `sshd_config` or `.env`.

## 4. Daily Security Ritual

Security is a daily reflex. Before starting work, run the verification script:
```bash
bash scripts/security_check.sh
```

This checks firewall status, secret scanning (via `ggshield`), and prompts for manual IDE verification.

## 5. Incident Response Decision Trees

### IF the AI runs a suspicious command:
**THEN:**
1. Click **Reject** in the Antigravity approval prompt.
2. Review the command for data exfiltration (`curl`, `nc`, `ping`).
3. If malicious, reset the IDE context entirely.

### IF a secret is accidentally committed to Git:
**THEN:**
1. Do not push to remote.
2. Run `git reset HEAD~1` to undo the commit.
3. If already pushed, consider the secret compromised. Rotate the key immediately.

### IF auditd alerts that `.env` was modified unexpectedly:
**THEN:**
1. Check `git diff` or `cat .env` to verify the changes.
2. If unauthorized, revert the file and check IDE logs.
