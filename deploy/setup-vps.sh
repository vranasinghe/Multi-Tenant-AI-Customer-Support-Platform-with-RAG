#!/usr/bin/env bash
# One-time hardening + Docker install for a fresh Ubuntu/Debian VPS. Run as root:
#     bash deploy/setup-vps.sh <deploy-username>
# Safe to re-run. It does NOT disable password SSH login until you have copied a key to
# the new user (see the checks below), so you cannot lock yourself out.
set -euo pipefail

DEPLOY_USER="${1:-deploy}"

if [ "$(id -u)" -ne 0 ]; then echo "Run as root." >&2; exit 1; fi

echo "==> Updating packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg ufw fail2ban unattended-upgrades git

echo "==> Swap (2 GB safety net for builds/crawls)"
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
  sysctl -p /etc/sysctl.d/99-swappiness.conf
fi

echo "==> Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi

echo "==> Deploy user '$DEPLOY_USER'"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
if [ -s /root/.ssh/authorized_keys ] && [ ! -s "/home/$DEPLOY_USER/.ssh/authorized_keys" ]; then
  cp /root/.ssh/authorized_keys "/home/$DEPLOY_USER/.ssh/authorized_keys"
  chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"
  chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
fi

echo "==> Firewall (22, 80, 443 only)"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

echo "==> fail2ban"
systemctl enable --now fail2ban

echo "==> Automatic security updates"
dpkg-reconfigure -f noninteractive unattended-upgrades || true

echo "==> SSH hardening"
if [ -s "/home/$DEPLOY_USER/.ssh/authorized_keys" ]; then
  cat > /etc/ssh/sshd_config.d/99-hardening.conf <<'EOF'
PasswordAuthentication no
PermitRootLogin no
EOF
  systemctl reload ssh || systemctl reload sshd
  echo "Password + root SSH login disabled. Log in as: ssh $DEPLOY_USER@<server-ip>"
else
  echo "WARNING: no SSH key found for $DEPLOY_USER; left password/root login enabled."
  echo "Copy your key (ssh-copy-id $DEPLOY_USER@<server-ip>), then re-run this script."
fi

echo "Done. Reconnect as $DEPLOY_USER so the docker group applies."
