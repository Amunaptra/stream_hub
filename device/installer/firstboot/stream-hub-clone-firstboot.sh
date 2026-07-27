#!/usr/bin/env bash
set -Eeuo pipefail

readonly DATA_DIR="/etc/stream-hub"
readonly MARKER="${DATA_DIR}/golden-image"
readonly CAPTURE_KEY_TAG="STREAM_HUB_IMAGE_CAPTURE_KEY"

log() {
  printf '[stream-hub-firstboot] %s\n' "$*"
}

[[ -e "${MARKER}" ]] || exit 0

log "Preparing cloned device identity"

network_interface="$(
  find /sys/class/net -mindepth 1 -maxdepth 1 -printf '%f\n' \
    | grep -v '^lo$' \
    | while read -r candidate; do
        [[ -r "/sys/class/net/${candidate}/address" ]] || continue
        address="$(tr -d ':' <"/sys/class/net/${candidate}/address")"
        [[ -n "${address}" && "${address}" != "000000000000" ]] || continue
        printf '%s\n' "${candidate}"
        break
      done
)"
[[ -n "${network_interface}" ]] || {
  log "No usable network interface was found"
  exit 1
}

mac_address="$(tr -d ':' <"/sys/class/net/${network_interface}/address")"
new_hostname="odroid-${mac_address: -6}"
printf '%s\n' "${new_hostname}" >/etc/hostname
hostname "${new_hostname}"
if grep -qE '^127\.0\.1\.1[[:space:]]' /etc/hosts; then
  sed -i -E "s/^127\\.0\\.1\\.1[[:space:]].*/127.0.1.1 ${new_hostname}/" /etc/hosts
else
  printf '127.0.1.1 %s\n' "${new_hostname}" >>/etc/hosts
fi

log "Generating machine and SSH identities"
rm -f /etc/machine-id /var/lib/dbus/machine-id
systemd-machine-id-setup
ln -s /etc/machine-id /var/lib/dbus/machine-id
rm -f /var/lib/systemd/random-seed
rm -f /etc/ssh/ssh_host_*
ssh-keygen -A

log "Removing source device registration"
rm -f \
  "${DATA_DIR}/device.json" \
  "${DATA_DIR}/command-results.json" \
  /run/stream-hub/*
rm -f \
  /etc/udev/rules.d/70-persistent-net.rules \
  /var/lib/dhcp/*.leases \
  /var/lib/NetworkManager/*.lease* \
  /run/systemd/netif/leases/*

for authorized_keys in /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys; do
  [[ -f "${authorized_keys}" ]] || continue
  sed -i "/${CAPTURE_KEY_TAG}/d" "${authorized_keys}"
done

root_device="$(findmnt -n -o SOURCE /)"
parent_name="$(lsblk -n -o PKNAME "${root_device}" | head -n 1)"
partition_number="$(lsblk -n -o PARTN "${root_device}" | head -n 1)"
if [[ -n "${parent_name}" && -n "${partition_number}" ]]; then
  log "Growing ${root_device} to fill /dev/${parent_name}"
  growpart "/dev/${parent_name}" "${partition_number}" || true
  resize2fs "${root_device}"
else
  log "Root partition layout is not supported for automatic growth; continuing"
fi

rm -f "${MARKER}"
sync
log "Clone preparation complete; rebooting with the new identity"
systemctl --no-block reboot
