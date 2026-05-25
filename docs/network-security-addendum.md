# UMI Exchange: Network Security Addendum

This document provides practical, low-cost guidance for securing the network environment where a self-hosted UMI instance runs. It is written for technical volunteers—those comfortable with the Linux command line and basic networking—who are helping churches, small nonprofits, and community groups deploy the UMI Exchange.

We know that a parish cannot afford enterprise hardware or a full-time security engineer. Therefore, this guide prioritizes open-source, affordable, and maintainable solutions. It focuses exclusively on the **network and infrastructure layers**; application-layer security (auth, encryption, audit logs) is already handled by the main codebase.

---

## 1. Threat Model for a Parish Self-Hosted Instance

Before configuring firewalls, we must understand what we are defending against. 

| Threat | Description | Mitigation |
|--------|-------------|------------|
| **Internet Scanning Bots** | Automated scripts constantly scanning the internet for open ports and vulnerable software. | Strict perimeter firewall rules (pfSense), UFW, Fail2ban. |
| **Compromised Coordinator Account** | An attacker guesses or steals a coordinator's password. | Two-Factor Authentication (2FA), VPN-only access to the dashboard. |
| **Wi-Fi Eavesdropping / Lateral Movement** | A guest on the parish public Wi-Fi tries to access the local server. | Network segmentation (VLANs), blocking local routing to the server. |
| **Physical Theft** | Someone physically steals the server hardware from the parish office. | Full-disk encryption (LUKS) on the server. |

---

## 2. Minimum Viable Security (30-Minute Quick Start)

If your parish has no dedicated IT person, start here. You can implement these steps in 30 minutes to achieve 80% of the security benefits.

1. **Enable UFW (Uncomplicated Firewall)**
   *Our `scripts/harden.sh` script does this automatically, but you can verify it.*
   ```bash
   sudo ufw status
   # Should only allow 22 (SSH), 80 (HTTP), and 443 (HTTPS)
   ```

2. **Install Tailscale for Admin Access**
   Tailscale is a zero-config VPN. Install it on the server and your laptop to create a secure, private network.
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```

3. **Enable Unattended Upgrades**
   Ensure the server automatically installs security patches.
   ```bash
   sudo apt install unattended-upgrades
   sudo dpkg-reconfigure --priority=low unattended-upgrades
   ```

4. **Simple Geo-Blocking**
   If your parish only serves your local area, you don't need traffic from across the globe. (See Section 6 for implementation).

---

## 3. Business Case: Why Invest in Security?

Why spend $50 on a managed switch or take a Saturday to set up pfSense? Because **trust is your only currency**.

Profitable, bootstrapped tech companies understand this. **Plausible Analytics** grew to over $1M+ ARR by making privacy and security their core selling points. **Healthchecks.io**, run by a solo founder generating $111k ARR, publishes exactly how their infrastructure is secured to build trust with developers. **Givebutter** raised $50M over 8 years largely because they proved to nonprofits that their donor data was safe.

For a parish handling sensitive mutual-aid requests (e.g., a domestic abuse survivor needing housing), a data breach destroys trust instantly. A $50 managed switch is negligible compared to the harm a breach would cause vulnerable populations.

---

## 4. Network Segmentation with VLANs

VLANs (Virtual Local Area Networks) act as separate, invisible cables running through the same physical switch. They ensure that someone on the Guest Wi-Fi cannot even "see" the UMI server on the network.

### Recommended Setup

```text
[Internet] → [Firewall (pfSense/OPNsense)] → [Managed Switch]
                                                │
                                                ├── VLAN 10: UMI Server (Trusted)
                                                ├── VLAN 20: Parish Office Staff (Management)
                                                └── VLAN 30: Guest Wi-Fi (No access to VLAN 10/20)
```

### Affordable Hardware
- **TP-Link Omada** or **Ubiquiti EdgeSwitch X** (~$50-$100)
- **MikroTik CSS** series (~$40)

### Configuration Example (Ubiquiti EdgeRouter CLI)
```bash
# Create VLAN 10 for the Server
set interfaces ethernet eth1 vif 10 address 10.0.10.1/24
set interfaces ethernet eth1 vif 10 description "UMI Server"

# Create VLAN 30 for Guest Wi-Fi
set interfaces ethernet eth1 vif 30 address 10.0.30.1/24
set interfaces ethernet eth1 vif 30 description "Guest WiFi"

# Prevent Guest Wi-Fi from reaching the Server
set firewall name GUEST_TO_LAN rule 10 action drop
set firewall name GUEST_TO_LAN rule 10 destination address 10.0.10.0/24
set interfaces ethernet eth1 vif 30 firewall in name GUEST_TO_LAN
commit; save
```

> **Hands-on Exercise:** Install VirtualBox. Create three VMs (a firewall using pfSense, an Ubuntu server, and an Ubuntu desktop client). Configure them on "Internal Networks" representing different VLANs and verify the client cannot ping the server until a rule allows it.

---

## 5. Firewall Rules (Beyond UFW)

While UFW runs on the server itself, a perimeter firewall (like **pfSense** or **OPNsense**) inspects traffic before it ever hits your server hardware. You can install pfSense for free on an old, repurposed PC with two network cards.

**Key pfSense Rules:**
1. **WAN Interface:** Allow incoming TCP 443 (HTTPS). Block everything else.
2. **WAN Interface:** Allow incoming TCP 80 (HTTP) *only* for Let's Encrypt renewal.
3. **LAN Interface:** Limit SSH (Port 22) access to specific IP addresses (e.g., the Parish Manager's static IP or the VPN subnet).

> **Hands-on Exercise:** In your pfSense VM, navigate to `Firewall > Rules > WAN`. Add a rule passing TCP port 443 to your UMI server. Use `nmap -Pn <WAN_IP>` from a client VM; only port 443 should show as `open`.

---

## 6. Geo-Blocking Implementation

If your community is in Ohio, you likely do not need web traffic from Russia or China. Geo-blocking stops massive amounts of automated bot traffic. 

If you use Caddy (as configured in the UMI repo), you can use the `caddy-maxmind-geolocation` plugin.

**Caddyfile Snippet:**
```caddy
(geofilter) {
    @blocked {
        not maxmind_country US CA
    }
    abort @blocked
}

umi.yourparish.org {
    import geofilter
    reverse_proxy app:8000
}
```
*Note: You must build Caddy with the maxmind module and configure the free MaxMind GeoLite2 database path.*

> **Warning:** Geo-blocking can lock out traveling volunteers. Always ensure your coordinators know how to use the VPN (Section 8) to bypass geo-blocks while traveling.

---

## 7. Access Control Lists (ACLs) for Admin Interfaces

The Django `/admin/` panel and the UMI `/dashboard/` should not be accessible to the general public. We can restrict them at the web-server layer using Caddy.

**Caddyfile Snippet for ACLs:**
```caddy
umi.yourparish.org {
    # Define an IP range (e.g., Parish Office or Tailscale VPN subnet)
    @admin_ips {
        remote_ip 192.168.20.0/24 100.64.0.0/10
    }

    # Match admin routes
    @admin_routes {
        path /admin/* /c/*/dashboard/*
    }

    # If it's an admin route AND NOT from an admin IP, forbid access
    handle @admin_routes {
        if not @admin_ips
        respond "Forbidden" 403
    }

    reverse_proxy app:8000
}
```

> **Hands-on Exercise:** Apply this Caddyfile rule. Try to access `domain.com/admin/` from your phone (cellular data). It should return 403 Forbidden. Connect to your Parish VPN or Wi-Fi; it should load normally.

---

## 8. VPN for Remote Coordinators

Coordinators need to manage the system from home. Exposing SSH or admin panels to the open internet is dangerous. Instead, use a VPN.

**Tailscale** is the easiest solution, but if you want to avoid third-party services, use **WireGuard** (built directly into the Linux kernel).

**Quick WireGuard Server Setup (Ubuntu):**
```bash
sudo apt install wireguard
# Generate keys
wg genkey | tee server_private.key | wg pubkey > server_public.key
```
Configure `/etc/wireguard/wg0.conf`:
```ini
[Interface]
Address = 10.8.0.1/24
ListenPort = 51820
PrivateKey = <server_private.key>

[Peer]
# Coordinator Laptop
PublicKey = <client_public.key>
AllowedIPs = 10.8.0.2/32
```
Once connected, the coordinator accesses the dashboard via `http://10.8.0.1`.

---

## 9. Monitoring and Simple Detection

You do not need a massive enterprise Security Information and Event Management (SIEM) system. Stick to lightweight, proven tools:

1. **Fail2ban:** (Included in `harden.sh`). Watches logs and temporarily bans IPs that repeatedly fail logins or scan for vulnerabilities.
2. **Auditd:** Tracks file modifications. 
   ```bash
   sudo apt install auditd
   # Monitor changes to Caddyfile
   sudo auditctl -w /etc/caddy/Caddyfile -p wa -k caddy_changes
   ```
3. **Logwatch:** (Included in `harden.sh`). Emails you a daily summary of disk space, SSH logins, and errors.

---

## 10. Physical Security and Air-Gapped Networks

Physical access defeats digital security. If the server sits on a desk in the parish lobby, anyone can plug in a USB drive and reboot it.
- **Minimum:** Keep the server in a locked closet.
- **Better:** Enable LUKS Full Disk Encryption during OS installation. If the machine is stolen, the data is unreadable.

**Air-Gapped Systems:** If the data is extraordinarily sensitive, UMI can run on a completely offline network (e.g., a laptop router that doesn't connect to the internet). Coordinators must physically be in the room to connect to the Wi-Fi and use it. *Trade-off: No remote access, no automated updates.*

---

## 11. Hands-On Lab: Complete Security Sandbox

Want to test this before buying hardware? Use this `Vagrantfile` to spin up a local network lab on your laptop.

Save as `Vagrantfile`:
```ruby
Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/jammy64"
  
  # UMI Server (VLAN 10 simulation)
  config.vm.define "umi_server" do |server|
    server.vm.network "private_network", ip: "192.168.10.10"
    server.vm.provision "shell", inline: <<-SHELL
      apt-get update
      apt-get install -y ufw docker.io
      ufw allow from 192.168.10.0/24
      ufw --force enable
    SHELL
  end

  # Untrusted Client (VLAN 30 simulation)
  config.vm.define "client" do |client|
    client.vm.network "private_network", ip: "192.168.30.10"
  end
end
```
Run `vagrant up` to build the lab. SSH into `client` and try to ping `192.168.10.10`. It will fail, proving that basic network segmentation works.

---

## 12. Quarterly Security Checklist

Set a calendar reminder for the first Saturday of every quarter to spend 30 minutes on this checklist:

- [ ] **Review Firewall Logs:** Check pfSense/UFW logs for excessive blocks from unexpected countries.
- [ ] **Audit VPN Access:** Remove WireGuard/Tailscale access for volunteers who have stepped down.
- [ ] **Test Restores:** Run `scripts/restore.sh` on a test machine to ensure your backups actually work.
- [ ] **Update OS:** Verify `unattended-upgrades` is running successfully (`grep unattended-upgrades /var/log/dpkg.log`).
- [ ] **Update GeoIP Data:** Ensure your `geoipupdate` cron job is fetching the latest country database.

---

## 13. References and Source Attribution

This addendum aligns with industry-standard compliance and benchmarks, scaled down for community use:

- **VLANs & Segmentation:** Based on *NIST SP 800-53 Control AC-4 (Information Flow Enforcement)*.
- **Firewall & Geo-Blocking:** Based on *NIST SP 800-53 Control SC-7 (Boundary Protection)*.
- **Auditd Monitoring:** Based on *NIST SP 800-53 Control SI-4 (Information System Monitoring)*.
- **Container Security:** Refer to the *CIS Docker Benchmark v1.6.0* for underlying container hardening.
- **Hardware & Software Docs:**
  - [pfSense Documentation](https://docs.netgate.com/pfsense/en/latest/)
  - [Caddy Server Security](https://caddyserver.com/docs/)
  - [WireGuard Quick Start](https://www.wireguard.com/quickstart/)

*By following this addendum, you are treating your community's data with the dignity and care it deserves.*
