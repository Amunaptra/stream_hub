#!/usr/bin/env bash
set -Eeuo pipefail

readonly INSTALL_ROOT="/opt/stream-hub"
readonly DATA_DIR="/var/lib/stream-hub"
readonly BACKUP_DIR="/var/backups/stream-hub"
readonly CONFIG_DIR="/etc/stream-hub"
readonly ENV_FILE="${CONFIG_DIR}/hub.env"
readonly SERVICE_USER="stream-hub"
readonly SOURCE_ROOT="${STREAM_HUB_SOURCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

log() { printf '\n[stream-hub-install] %s\n' "$*"; }
fail() { printf '\n[stream-hub-install] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || fail "Run as root: sudo ./install.sh"
command -v apt-get >/dev/null || fail "This installer currently supports Debian/Ubuntu systems"

log "Installing Hub runtime packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  openssl \
  python3 \
  python3-pip \
  python3-venv

log "Creating protected service account and directories"
getent group "${SERVICE_USER}" >/dev/null || groupadd --system "${SERVICE_USER}"
id "${SERVICE_USER}" >/dev/null 2>&1 || \
  useradd --system --gid "${SERVICE_USER}" --home-dir "${DATA_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
usermod -a -G "${SERVICE_USER}" "${SERVICE_USER}"
install -d -o root -g root -m 0755 "${INSTALL_ROOT}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0750 "${DATA_DIR}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0700 "${BACKUP_DIR}"
install -d -o root -g "${SERVICE_USER}" -m 0750 "${CONFIG_DIR}"

log "Preserving or creating Hub administrator configuration"
if [[ ! -f "${ENV_FILE}" ]]; then
  ADMIN_TOKEN="$(openssl rand -hex 32)"
  cat >"${ENV_FILE}" <<EOF
STREAM_HUB_ADMIN_TOKEN=${ADMIN_TOKEN}
STREAM_HUB_DATABASE=${DATA_DIR}/hub.sqlite3
STREAM_HUB_UI_DIR=${INSTALL_ROOT}/hub/ui
STREAM_HUB_PORT=8788
STREAM_HUB_MDNS=1
STREAM_HUB_SECURE_COOKIE=0
EOF
fi
chown root:"${SERVICE_USER}" "${ENV_FILE}"
chmod 0640 "${ENV_FILE}"

log "Installing Hub application without replacing database or credentials"
rm -rf "${INSTALL_ROOT}/hub"
cp -a "${SOURCE_ROOT}/hub" "${INSTALL_ROOT}/hub"
chown -R root:root "${INSTALL_ROOT}/hub"
if [[ ! -x "${INSTALL_ROOT}/venv/bin/python" ]]; then
  python3 -m venv "${INSTALL_ROOT}/venv"
fi
"${INSTALL_ROOT}/venv/bin/pip" install --upgrade pip
"${INSTALL_ROOT}/venv/bin/pip" install "${INSTALL_ROOT}/hub/backend"

log "Installing bounded logs and daily SQLite backups"
install -d -o root -g root -m 0755 /etc/systemd/journald.conf.d
install -o root -g root -m 0644 \
  "${SOURCE_ROOT}/hub/installer/journald.conf" \
  /etc/systemd/journald.conf.d/stream-hub-storage.conf
install -o root -g root -m 0644 \
  "${SOURCE_ROOT}/hub/installer/systemd/stream-hub.service" \
  /etc/systemd/system/stream-hub.service
install -o root -g root -m 0644 \
  "${SOURCE_ROOT}/hub/installer/systemd/stream-hub-backup.service" \
  /etc/systemd/system/stream-hub-backup.service
install -o root -g root -m 0644 \
  "${SOURCE_ROOT}/hub/installer/systemd/stream-hub-backup.timer" \
  /etc/systemd/system/stream-hub-backup.timer

systemctl daemon-reload
systemctl restart systemd-journald
systemctl enable --now stream-hub.service stream-hub-backup.timer

log "Validating Hub"
systemctl is-active --quiet stream-hub.service || fail "stream-hub.service failed"
curl --fail --silent http://127.0.0.1:8788/healthz >/dev/null || fail "Hub health check failed"
curl --fail --silent http://127.0.0.1:8788/ui/ >/dev/null || fail "Hub UI check failed"

IP="$(hostname -I | awk '{print $1}')"
printf '\nInstallation complete. Dashboard: http://%s:8788/ui/\n' "${IP}"
printf 'Administrator token: grep STREAM_HUB_ADMIN_TOKEN %s\n' "${ENV_FILE}"
