# Network Security Addendum: UMI Exchange Reference Implementation

This document provides practical, low-cost network and infrastructure security guidance for self-hosting the UMI Exchange. It is designed for technical volunteers (e.g., parish coordinators, community organizers, or local sysadmins) who are comfortable with the Linux command line and basic networking concepts. 

The application-layer security measures (such as encrypted metadata fields, role-based access control, and database-level audit log protections) are already integrated into the core UMI Exchange Django codebase. This addendum focuses exclusively on the **network and infrastructure layers** to shield the deployment from external threats, segregate traffic on local networks, and enable secure administration.

---

## 1. Threat Model for a Parish Self-Hosted Instance

Self-hosting in a community environment (like a church basement, a local food pantry, or a neighborhood center) introduces threats that differ from commercial cloud hosting. Below is a mapping of common threats to specific infrastructure-layer mitigations.

| Threat Actor / Event | Vulnerability | Impact | Mitigation |
| :--- | :--- | :--- | :--- |
| **Wi-Fi Eavesdropper** | Guest Wi-Fi clients on the same subnet as the UMI server. | Eavesdropping on unencrypted local management traffic, potential lateral movement, or denial of service. | **VLAN Segmentation** (Section 4): Isolate the server from the guest wireless network. |
| **Internet Scanning Bots** | Shodan, Censys, or automated brute-force bots targeting public IP addresses. | Brute-force attempts against SSH (port 22) or discovery of application-layer vulnerabilities. | **Firewalling & Geo-blocking** (Sections 5 & 6) and **VPN-Only Access** (Section 8). |
| **Compromised Coordinator Account** | Compromised credentials via phishing or password reuse. | Unauthorized access to mutual aid participant records and contact details. | **2FA Enforcement** (Application) + **Admin Access Control Lists** (Section 7) to restrict admin URLs. |
| **Physical Theft / Intrusion** | Server hardware located in an unlocked closet or shared office. | Unauthorized extraction of SQLite database files or configuration secrets directly from storage. | **Full-Disk Encryption (LUKS)** (Section 10) + **Physical hardening**. |

---

## 2. Minimum Viable Security (30-Minute Quick Start)

If your community has no dedicated IT administrator, complete this **Minimum Viable Security** checklist immediately upon deployment. This takes approximately 30 minutes and relies entirely on free, open-source utilities.

### Checklist
1. **Enable the Host Firewall (UFW)**: Block all incoming traffic by default, allowing only HTTPS and SSH.
2. **Install Tailscale**: Restrict SSH and Django administration to a private mesh network.
3. **Configure Geo-blocking**: Allow requests only from your home country at the reverse proxy layer.
4. **Set Up Unattended-Upgrades**: Ensure critical security patches are installed daily.

### Step-by-Step Commands

```bash
# 1. Enable UFW Host Firewall (If not already completed by harden.sh)
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 80/tcp comment 'Allow Let-Encrypt challenges'
sudo ufw allow 443/tcp comment 'Allow public HTTPS'
sudo ufw allow 22/tcp comment 'Temporary SSH access'
sudo ufw --force enable

# 2. Install Tailscale for Secure Management
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 3. Restrict SSH to the Tailscale Interface
# Find your Tailscale interface name (usually 'tailscale0')
ip addr show dev tailscale0
# Allow SSH ONLY through Tailscale, then block public SSH
sudo ufw allow in on tailscale0 to any port 22 comment 'Secure SSH via Tailscale'
sudo ufw delete allow 22/tcp
sudo ufw reload

# 4. Enable Daily Automated OS Security Updates
sudo apt-get update && sudo apt-get install -y unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

### Caddyfile Geo-Blocking Snippet
Add this configuration snippet to your `/etc/caddy/Caddyfile` to drop requests originating outside your country (e.g., US) using the `client_ip` block:

```caddy
# Example /etc/caddy/Caddyfile
example.umi-exchange.org {
    # Matcher for allowed country block (replace with your country code)
    # Note: Requires caddy-dns / geoip module or Cloudflare geo headers if proxying
    @outside_us {
        not client_ip geoip country US
    }
    respond @outside_us "Access Denied by Regional Security Policy" 403

    reverse_proxy localhost:8000
}
```

---

## 3. Business Case – Why Invest More?

In community mutual aid, **trust is the currency**. The UMI Exchange stores information about vulnerable populations: families requesting food assistance, seniors needing help with home repairs, and residents sharing temporary shelter. A security breach that exposes their physical addresses, phone numbers, or household needs destroys the community’s trust.

### Real-World Open-Source Benchmarks
Security is not just a defensive cost; it is a foundational trust-builder that enables sustainable operations:
*   **Healthchecks.io**: A bootstrapped cron-monitoring tool run by a solo founder, generating over **$111k ARR**. Their primary value proposition is rock-solid reliability and privacy-preserving alerting. By demonstrating strict security hygiene, they won the trust of corporate and individual developers alike.
*   **Plausible Analytics**: Built a privacy-first web analytics platform that scaled to over **$1M+ ARR** by offering a trust-based alternative to Google Analytics. Their commitment to infrastructure privacy and transparency made their product highly marketable.
*   **Givebutter**: A community fundraising platform that grew to raise **$50M** after 8 years of operation. Their survival and growth depended on maintaining PCI-compliant infrastructure and secure transaction layers, proving that volunteer networks and small nonprofits demand the same level of security as financial institutions.

For a parish, investing **$50** in a managed switch and a few hours of configuration is negligible compared to the reputational and physical harm a data breach would bring to local households.

---

## 4. Network Segmentation with VLANs

By default, most residential or small office networks use a single flat subnet (`192.168.1.0/24`). If a visitor connects to the Guest Wi-Fi and gets compromised, they can scan, query, and attack your UMI server. **VLANs (Virtual Local Area Networks)** solve this by dividing a single physical switch into separate isolated networks.

### Recommended Architecture

```
                 [ Internet ]
                      │
            [ Firewall (pfSense) ]
                      │
             [ Managed Switch ]
             /        │        \
      (VLAN 10)   (VLAN 20)   (VLAN 30)
         │            │            │
    [UMI Server]  [Office PC]  [Guest Wi-Fi]
```

*   **VLAN 10 (Server)**: Isolated DMZ. Contains only the UMI Exchange server. No local devices can talk to it except over specific routed management ports.
*   **VLAN 20 (Management/Office)**: Trusted devices (Parish staff computers). Allowed to access the UMI server's SSH and Admin dashboard.
*   **VLAN 30 (Guest Wi-Fi)**: Completely untrusted. Can access the public internet, but firewall rules drop all traffic headed to VLAN 10 or 20.

### Configuration Examples

#### 1. Ubiquiti EdgeRouter (CLI)
Configure an EdgeRouter to route traffic for VLAN 10 (Server) and VLAN 20 (Office) on physical port `eth1`:

```bash
# Define VLAN 10 Interface
set interfaces ethernet eth1 vif 10 address 10.10.10.1/24
set interfaces ethernet eth1 vif 10 description "UMI Server Network"

# Define VLAN 20 Interface
set interfaces ethernet eth1 vif 20 address 10.20.20.1/24
set interfaces ethernet eth1 vif 20 description "Office Management"

# Block VLAN 10 from accessing VLAN 20
set firewall name UMI_IN rule 10 action drop
set firewall name UMI_IN rule 10 description "Block UMI Server to Office"
set firewall name UMI_IN rule 10 destination address 10.20.20.0/24
set firewall name UMI_IN rule 10 protocol all
commit; save
```

#### 2. OpenWRT (`/etc/config/network`)
If you are using an old router flashed with OpenWRT, configure VLANs inside `/etc/config/network`:

```ini
config device
    option name 'lan.10'
    option type 'vlan'
    option ifname 'lan'
    option vid '10'

config interface 'umi_vlan'
    option proto 'static'
    option device 'lan.10'
    option ipaddr '10.10.10.1'
    option netmask '255.255.255.0'

config device
    option name 'lan.20'
    option type 'vlan'
    option ifname 'lan'
    option vid '20'

config interface 'office_vlan'
    option proto 'static'
    option device 'lan.20'
    option ipaddr '10.20.20.1'
    option netmask '255.255.255.0'
```

---

### Hands-On Exercise: Virtual Network Segmentation Lab

In this exercise, you will configure virtual VLAN interfaces on a single Linux machine to simulate network separation.

**Goal**: Build two isolated virtual networks and verify that traffic cannot flow between them without routing.

1. **Create Virtual Interfaces**:
   ```bash
   sudo ip link add link eth0 name eth0.10 type vlan id 10
   sudo ip link add link eth0 name eth0.20 type vlan id 20
   ```
2. **Assign IP Addresses**:
   ```bash
   sudo ip addr add 10.10.10.2/24 dev eth0.10
   sudo ip addr add 10.20.20.2/24 dev eth0.20
   ```
3. **Bring Interfaces Up**:
   ```bash
   sudo ip link set dev eth0.10 up
   sudo ip link set dev eth0.20 up
   ```
4. **Test Separation**:
   Try to ping from VLAN 10's subnet to VLAN 20.
   ```bash
   ping -I eth0.10 10.20.20.2 -c 3
   # Expected output: Destination Host Unreachable
   ```

---

## 5. Firewall Rules (Beyond Host Firewalls)

While `harden.sh` configures the host-level UFW firewall, a dedicated perimeter firewall (like pfSense or OPNsense) adds a critical layer of defense. It prevents internal network scanning, handles intrusion detection, and manages centralized access policies.

### Recommended pfSense Rule Matrix

Configure your pfSense interfaces under **Firewall > Rules**:

| Interface | Protocol | Source | Port | Destination | Port | Action | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **WAN** | TCP | Any | * | WAN Address | 443 | **PASS** | Allow Public HTTPS |
| **WAN** | TCP | Any | * | WAN Address | 80 | **PASS** | Allow Public HTTP (Let's Encrypt redirection) |
| **WAN** | TCP | VPN_IPs | * | UMI_Server | 22 | **PASS** | Allow SSH from VPN / Static Coordinator IP only |
| **WAN** | * | Any | * | Any | * | **BLOCK** | Default Deny All incoming |
| **VLAN10** | * | UMI_Server | * | VLAN20_Subnet| * | **REJECT**| Prevent UMI Server from initiating local connections |
| **VLAN10** | * | UMI_Server | * | Any | * | **PASS** | Allow Server internet access (for updates) |

---

### Hands-On Exercise: Firewalled DMZ Validation

Verify that your perimeter firewall blocks unauthorized scan attempts against the UMI server.

1. Install `nmap` on a test client machine (representing an external attacker or guest Wi-Fi user):
   ```bash
   sudo apt-get install -y nmap
   ```
2. Run a TCP port scan against the public IP or server IP:
   ```bash
   nmap -p 22,80,443,5432,6379 10.10.10.2
   ```
3. **Verify the Results**:
   * Ports `80` and `443` should show as `open`.
   * Port `22` (SSH) should show as `filtered` or `closed` unless scanning from an allowed management subnet.
   * Internal services like PostgreSQL (`5432`) and Redis (`6379`) must report `filtered` or `closed`.

---

## 6. Geo-Blocking Implementation

Geo-blocking significantly reduces background automated attacks by rejecting network traffic originating from countries where your community members do not live.

### Caddy GeoIP Integration
Caddy supports MaxMind GeoIP matching. To use it, compile Caddy with the `geoip` module using `xcaddy`:

```bash
# 1. Install xcaddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
# Build Caddy with geoip support
xcaddy build --with github.com/porech/caddy-maxmind-geoip
```

### Automatic GeoIP Updates (`geoipupdate`)
Sign up for a free MaxMind account, obtain a License Key, and install the client:

```bash
sudo apt-get install -y geoipupdate
```
Edit `/etc/GeoIP.conf` with your account credentials:
```ini
AccountID YOUR_ACCOUNT_ID
LicenseKey YOUR_LICENSE_KEY
EditionIDs GeoLite2-Country GeoLite2-City
```
Set up a weekly cron job to update the database:
```bash
echo "0 3 * * 3 root /usr/bin/geoipupdate" | sudo tee /etc/cron.d/geoipupdate
```

### Native Firewall Blocking (`nftables` + `ipset`)
If you want to drop traffic before it even reaches Caddy, use `nftables` combined with a country IP list:

```bash
# Install iprange tool
sudo apt-get install -y iprange

# Download country CIDR lists (e.g., US zones)
curl -o us.zone http://www.ipdeny.com/ipblocks/data/countries/us.zone

# Create nftables ruleset file (/etc/nftables.conf)
cat << 'EOF' | sudo tee /etc/nftables.conf
table ip filter {
    set allowed_countries {
        type ipv4_addr
        flags interval
        elements = {
            # Populate with ranges from us.zone
        }
    }
    chain input {
        type filter hook input priority 0; policy drop;
        
        # Allow loopback, established connections
        iif lo accept
        ct state established,related accept
        
        # Filter incoming HTTP/HTTPS traffic
        tcp dport {80, 443} ip saddr @allowed_countries accept
        
        # Log and drop everything else
        log prefix "Dropped-by-GeoIP: " flags all drop
    }
}
EOF
sudo systemctl enable nftables && sudo systemctl restart nftables
```

> [!WARNING]
> **Geo-blocking Gotchas**: If a parish coordinator travels internationally, or uses a commercial VPN that routes traffic through servers in another country, they will be blocked. Ensure a clear process is documented to bypass geo-blocking via Tailscale or specific firewall exceptions.

---

## 7. Access Control Lists (ACLs) for Admin Interfaces

Django’s `/admin/` and the coordinator dashboard (`/c/<slug>/dashboard/`) are high-value targets. Even with strong passwords and 2FA, restricting these paths to specific IP subnets provides defense-in-depth.

### Caddy ACL Configuration
Restrict the `/admin/` URL prefix to the local parish office subnet (`10.20.20.0/24`) and private VPN ranges:

```caddy
# /etc/caddy/Caddyfile
example.umi-exchange.org {
    # Matchers
    @admin_paths {
        path /admin/*
        path /c/*/dashboard/*
    }
    
    # Block unauthorized admin requests
    handle @admin_paths {
        @unauthorized not client_ip 10.20.20.0/24 100.64.0.0/10
        respond @unauthorized "Forbidden: Management Network Only" 403
    }
    
    reverse_proxy localhost:8000
}
```

### Nginx ACL Configuration
If using Nginx as a reverse proxy:

```nginx
server {
    listen 443 ssl;
    server_name example.umi-exchange.org;

    location / {
        proxy_pass http://localhost:8000;
    }

    # Restrict Django admin portal
    location /admin/ {
        allow 10.20.20.0/24;    # Parish Office Subnet
        allow 100.64.0.0/10;    # Tailscale VPN Subnet
        deny all;
        proxy_pass http://localhost:8000;
    }
}
```

---

## 8. VPN for Remote Coordinators

A Virtual Private Network (VPN) allows coordinators working from home to access the management interface of the UMI server securely over an encrypted tunnel.

### WireGuard Installation & Setup

1. **Install WireGuard** on the Ubuntu host:
   ```bash
   sudo apt-get update && sudo apt-get install -y wireguard
   ```
2. **Generate Private and Public Keys**:
   ```bash
   umask 077
   wg genkey | tee server_private.key | wg pubkey > server_public.key
   wg genkey | tee client_private.key | wg pubkey > client_public.key
   ```
3. **Configure the Server Interface (`/etc/wireguard/wg0.conf`)**:
   ```ini
   [Interface]
   PrivateKey = SERVER_PRIVATE_KEY_CONTENT
   Address = 10.8.0.1/24
   ListenPort = 51820
   
   # Server forwarding rules
   PostUp = ufw route allow in on wg0
   PostDown = ufw route delete allow in on wg0

   [Peer]
   # Remote coordinator client
   PublicKey = CLIENT_PUBLIC_KEY_CONTENT
   AllowedIPs = 10.8.0.2/32
   ```
4. **Enable IP Forwarding & Start Interface**:
   ```bash
   echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
   sudo sysctl -p
   sudo systemctl enable wg-quick@wg0
   sudo systemctl start wg-quick@wg0
   ```

### Client Profile (`wg0-client.conf` for Windows/macOS/Linux)
Distribute this file securely to the remote coordinator:

```ini
[Interface]
PrivateKey = CLIENT_PRIVATE_KEY_CONTENT
Address = 10.8.0.2/24
DNS = 1.1.1.1

[Peer]
PublicKey = SERVER_PUBLIC_KEY_CONTENT
Endpoint = PUBLIC_IP_OF_PARISH_ROUTER:51820
AllowedIPs = 10.8.0.0/24, 10.10.10.0/24
PersistentKeepalive = 25
```

---

## 9. Monitoring and Simple Detection

Because full Intrusion Detection Systems (like Snort or Zeek) consume significant hardware resources, a parish should rely on lightweight host audit logging and simple detection tools.

### `auditd` Configuration for File Integrity Monitoring
Monitor updates to configuration files like Caddyfile and Docker files to detect unauthorized changes.

1. **Install Auditd**:
   ```bash
   sudo apt-get install -y auditd audispd-plugins
   ```
2. **Create Audit Rules** (`/etc/audit/rules.d/umi.rules`):
   ```
   # Monitor changes to Caddy config
   -w /etc/caddy/Caddyfile -p wa -k caddy_changed
   
   # Monitor docker-compose files
   -w /home/umi/umi-exchange/docker-compose.prod.yml -p wa -k docker_changed
   
   # Monitor SSH key modifications
   -w /home/umi/.ssh/authorized_keys -p wa -k ssh_keys_changed
   ```
3. **Restart Service & Query Logs**:
   ```bash
   sudo systemctl restart auditd
   # Search audit logs for changes
   ausearch -k caddy_changed -i
   ```

### Deploying a Lightweight SSH Honeypot
Deploy an SSH honeypot to capture scanning bots and block them before they discover the real SSH port (which you moved to Tailscale or WireGuard).

Add a honeypot configuration using a small Python listener or `cowrie` inside a Docker container:

```yaml
# docker-compose.prod.yml extension for SSH Honeypot
services:
  honeypot:
    image: cowrie/cowrie:latest
    ports:
      - "22:2222" # Listen on standard port 22
    restart: always
    environment:
      - COWRIE_TELNET_ENABLED=false
```

---

## 10. Physical Security and Air-Gapped Networks

Cloud-based security protections are useless if the physical server can be carried out of an office by an intruder.

### Physical Hardening Recommendations
1. **Server Location**: Place the host server in a locked closet or cabinet. Ensure it is off the floor to prevent water damage.
2. **BIOS/UEFI Passwords**: Restrict boot priorities in the BIOS. Require a supervisor password to edit settings, preventing attackers from booting into live Linux distros using USB drives.
3. **Full-Disk Encryption**: Ensure LUKS (Linux Unified Key Setup) is enabled during OS installation.

### Air-Gapped (Offline Intranet) Deployments
For community sites in remote areas or high-privacy networks, you can run UMI as a localized intranet node.

#### How to Synchronize Data Offline
1. **Intranet Access Only**: Server is connected to a local access point without a WAN gateway interface. All network endpoints resolve locally (e.g., `http://umi.local`).
2. **Manual Synchronization Utility**: Write a local script to export database audit logs and state logs to an encrypted USB drive:
   ```bash
   # Export script
   gpg --symmetric --cipher-algo AES256 -o /media/usb/umi-export-$(date +%F).sql.gpg db.sqlite3
   ```
3. **Operational Warning**: Running an offline network prevents automatic software updates, SMS notification relays, and offsite backups. Only use this if WAN access is impossible.

---

## 11. Hands-On Lab: Complete Security Sandbox

Volunteers can test this entire infrastructure configuration locally inside a VM sandbox environment before deploying it to physical hardware.

### Sandbox Architecture
*   **pfSense VM**: Manages the WAN (bridged to host internet) and separate internal subnets for UMI (VLAN 10) and Clients (VLAN 20).
*   **UMI Server VM**: Runs the Django app inside Docker on VLAN 10.
*   **Client VM**: Simulates an administrator trying to connect on VLAN 20.

### Vagrantfile Setup
Create a `Vagrantfile` inside your test directory to build the virtual networking infrastructure:

```ruby
# Vagrantfile
Vagrant.configure("2") do |config|
  # UMI Server Host on VLAN 10
  config.vm.define "umi_host" do |umi|
    umi.vm.box = "ubuntu/focal64"
    umi.vm.hostname = "umi-host"
    # Custom private network representing VLAN 10 interface
    umi.vm.network "private_network", ip: "10.10.10.5", virtualbox__intnet: "vlan10"
  end

  # Test Client Host on VLAN 20
  config.vm.define "client_host" do |client|
    client.vm.box = "ubuntu/focal64"
    client.vm.hostname = "client-host"
    client.vm.network "private_network", ip: "10.20.20.5", virtualbox__intnet: "vlan20"
  end
end
```

### Ansible Sandbox Configuration Playbook
Use this Ansible playbook (`configure-sandbox.yml`) to automatically configure UFW, GeoIP simulation, and WireGuard:

```yaml
- name: Configure Sandbox Infrastructure
  hosts: all
  become: true
  tasks:
    - name: Update apt cache
      apt:
        update_cache: yes

    - name: Install dependencies
      apt:
        name:
          - ufw
          - wireguard
          - fail2ban
        state: present

    - name: Configure basic UFW rules
      ufw:
        rule: allow
        port: "{{ item }}"
        proto: tcp
      loop:
        - '80'
        - '443'

    - name: Deny local routing traffic between subnets
      ufw:
        rule: deny
        direction: in
        interface: eth1
        to_ip: 10.20.20.0/24
```

To run the sandbox lab:
```bash
vagrant up
ansible-playbook -i .vagrant/provisioners/ansible/inventory/vagrant_ansible_inventory configure-sandbox.yml
```

---

## 12. Quarterly Security Checklist

Provide this checklist to the community technical volunteer. Review these items every quarter to verify the ongoing security of the infrastructure.

*   [ ] **Review Firewall Logs**: Check pfSense dashboard for any unusual blocking spikes on unexpected ports.
*   [ ] **Verify OS Updates**: Verify that the daily unattended-upgrades service is running:
    ```bash
    cat /var/log/unattended-upgrades/unattended-upgrades.log
    ```
*   [ ] **Perform Backup Restoration Test**: Do not just verify that backup files are generated. Download the latest backup (`scripts/backup.sh`) and restore it on a separate sandbox machine (`scripts/restore.sh`) to confirm integrity.
*   [ ] **Revoke Old VPN Access**: Audit Tailscale/WireGuard profiles. Delete profiles for volunteers who are no longer active in the community.
*   [ ] **Update GeoIP Database**: Check that MaxMind weekly download updates are executing correctly.
*   [ ] **Inspect Audit Logs**: Run `ausearch -k caddy_changed -i` to confirm no configuration files were changed.

---

## 13. References and Source Attribution

This addendum is informed by the following specifications, standards, and benchmarks:

*   **NIST SP 800-53 (Rev 5)**:
    *   *AC-4 (Information Flow Enforcement)*: Implemented via VLAN segmentation and pfSense rules.
    *   *SC-7 (Boundary Protection)*: Implemented via perimeter firewall configurations.
    *   *SC-10 (Network Network Access)*: Addressed using WireGuard and Tailscale encryption.
    *   *SI-4 (Information System Monitoring)*: Covered by fail2ban, auditd, and Honeypot logging.
*   **CIS Benchmarks**:
    *   *CIS Ubuntu Linux Benchmark v2.0.0*: Section 3.5 (Configure Firewall) and Section 5.1 (Configure System Accounting - `auditd`).
    *   *CIS Docker Benchmark v1.6.0*: Section 2.1 (Ensure network traffic is restricted between containers).
*   **Official Documentation Pages**:
    *   [pfSense Community Edition Guide](https://docs.netgate.com/pfsense/en/latest/)
    *   [Caddy Security & Client Matchers](https://caddyserver.com/docs/caddyfile/matchers)
    *   [WireGuard Quickstart Docs](https://www.wireguard.com/quickstart/)
*   **Free Learning Resources**:
    *   *Cisco Networking Academy*: Intro to Cybersecurity & Basic Network Operations.
    *   *Network Chuck / YouTube Security Playlists*: Hands-on introductions to WireGuard tunnels, VLAN setup, and OPNsense configurations.
