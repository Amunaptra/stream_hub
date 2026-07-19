#!/usr/bin/env bash
set -Eeuo pipefail

readonly INSTALL_ROOT="/opt/stream-hub-device"
readonly DATA_DIR="/etc/stream-hub"
readonly JOURNAL_DROPIN="/etc/systemd/journald.conf.d/stream-hub-storage.conf"
readonly AGENT_USER="stream-agent"
readonly SHARED_GROUP="stream-hub"
readonly PLAYER_USER="${PLAYER_USER:-odroid}"
readonly SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

log() { printf '\n[stream-hub-install] %s\n' "$*"; }
fail() { printf '\n[stream-hub-install] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || fail "Run as root: sudo ./device/installer/install.sh"
command -v apt-get >/dev/null || fail "This installer currently supports Debian/Ubuntu systems"
id "${PLAYER_USER}" >/dev/null 2>&1 || fail "Player user '${PLAYER_USER}' does not exist"

log "Installing operating-system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates \
  ffmpeg \
  mpv \
  python3 \
  python3-pip \
  python3-venv \
  sudo

log "Creating service accounts and protected directories"
getent group "${SHARED_GROUP}" >/dev/null || groupadd --system "${SHARED_GROUP}"
id "${AGENT_USER}" >/dev/null 2>&1 || \
  useradd --system --home-dir "${INSTALL_ROOT}" --shell /usr/sbin/nologin "${AGENT_USER}"
usermod -a -G "${SHARED_GROUP}" "${AGENT_USER}"
usermod -a -G "${SHARED_GROUP}" "${PLAYER_USER}"
for group in video audio render; do
  getent group "${group}" >/dev/null && usermod -a -G "${group}" "${PLAYER_USER}"
done

install -d -o root -g root -m 0755 "${INSTALL_ROOT}"
install -d -o root -g "${SHARED_GROUP}" -m 2770 "${DATA_DIR}"

log "Installing application source without replacing device data"
rm -rf "${INSTALL_ROOT}/device"
cp -a "${SOURCE_ROOT}/device" "${INSTALL_ROOT}/device"
install -m 0644 "${SOURCE_ROOT}/pyproject.toml" "${INSTALL_ROOT}/pyproject.toml"
install -m 0644 "${SOURCE_ROOT}/requirements-device.txt" "${INSTALL_ROOT}/requirements-device.txt"

if [[ ! -x "${INSTALL_ROOT}/venv/bin/python" ]]; then
  python3 -m venv "${INSTALL_ROOT}/venv"
fi
"${INSTALL_ROOT}/venv/bin/pip" install --upgrade pip
"${INSTALL_ROOT}/venv/bin/pip" install \
  --constraint "${INSTALL_ROOT}/requirements-device.txt" \
  "${INSTALL_ROOT}"

if [[ ! -f "${DATA_DIR}/playlist.json" ]]; then
  install -o root -g "${SHARED_GROUP}" -m 0660 /dev/null "${DATA_DIR}/playlist.json"
  printf '%s\n' '{"revision": 0, "default_seconds": 20, "streams": []}' > "${DATA_DIR}/playlist.json"
fi
chown root:"${SHARED_GROUP}" "${DATA_DIR}/playlist.json"
chmod 0660 "${DATA_DIR}/playlist.json"

log "Installing bounded seven-day journal policy"
install -d -o root -g root -m 0755 /etc/systemd/journald.conf.d
install -o root -g root -m 0644 \
  "${SOURCE_ROOT}/device/installer/journald/stream-hub-storage.conf" \
  "${JOURNAL_DROPIN}"

log "Installing systemd services and restricted privilege rules"
install -o root -g root -m 0644 \
  "${SOURCE_ROOT}/device/installer/systemd/stream-player.service" \
  /etc/systemd/system/stream-player.service
install -o root -g root -m 0644 \
  "${SOURCE_ROOT}/device/installer/systemd/stream-agent.service" \
  /etc/systemd/system/stream-agent.service

cat >/etc/sudoers.d/stream-hub-agent <<'EOF'
stream-agent ALL=(root) NOPASSWD: /usr/bin/systemctl is-active stream-player.service
stream-agent ALL=(root) NOPASSWD: /usr/bin/systemctl restart stream-player.service
stream-agent ALL=(root) NOPASSWD: /usr/bin/systemctl reboot
EOF
chmod 0440 /etc/sudoers.d/stream-hub-agent
visudo -cf /etc/sudoers.d/stream-hub-agent >/dev/null

systemctl daemon-reload
systemctl restart systemd-journald
systemctl disable --now getty@tty1.service >/dev/null 2>&1 || true
systemctl enable --now stream-player.service stream-agent.service

log "Validating installation"
systemctl is-active --quiet stream-player.service || fail "stream-player.service failed"
systemctl is-active --quiet stream-agent.service || fail "stream-agent.service failed"
curl --fail --silent http://127.0.0.1:8787/healthz >/dev/null || fail "agent health check failed"

printf '\nInstallation complete. Device identity: %s\n' "${DATA_DIR}/device.json"
printf 'Agent health: http://127.0.0.1:8787/healthz\n'
