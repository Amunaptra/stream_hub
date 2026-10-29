#!/usr/bin/env bash
set -Eeuo pipefail

readonly SOURCE_IMAGE="${STREAM_HUB_SOURCE_IMAGE:?source public image required}"
readonly RELEASE_DIR="${STREAM_HUB_RELEASE_DIR:?release directory required}"
readonly PACKAGE="${STREAM_HUB_ODROID_PACKAGE:?Odroid package required}"
readonly VERSION="${STREAM_HUB_VERSION:?version required}"
readonly HUB_URL="${STREAM_HUB_IMAGE_HUB_URL:?Hub URL required}"
readonly OUTPUT="${RELEASE_DIR}/stream-hub-odroid-c4-v${VERSION}-public.img"
readonly PARTIAL="${OUTPUT}.partial"
readonly MOUNT_DIR="${STREAM_HUB_IMAGE_MOUNT_DIR:-/mnt/stream-hub-image-build}"

work="$(mktemp -d /tmp/stream-hub-image-build.XXXXXX)"
loop=""

cleanup() {
  sync || true
  mountpoint -q "${MOUNT_DIR}" && umount "${MOUNT_DIR}" || true
  [[ -z "${loop}" ]] || losetup -d "${loop}" 2>/dev/null || true
  rm -rf "${work}"
}
trap cleanup EXIT

fsck_fix() {
  local status=0
  e2fsck -fy "$1" || status=$?
  [[ "${status}" -le 1 ]] || return "${status}"
}

fsck_read_only() {
  local status=0
  e2fsck -fn "$1" || status=$?
  [[ "${status}" -le 1 ]] || return "${status}"
}

mkdir -p "${RELEASE_DIR}" "${MOUNT_DIR}"
rm -f "${PARTIAL}" "${OUTPUT}.zst"

echo IMAGE_COPY_START
cp --reflink=auto --sparse=always "${SOURCE_IMAGE}" "${PARTIAL}"
echo IMAGE_COPY_DONE

loop="$(losetup --find --show --partscan "${PARTIAL}")"
fsck_fix "${loop}p2"
mount "${loop}p2" "${MOUNT_DIR}"

tar -xzf "${PACKAGE}" -C "${work}"
package_root="${work}/stream-hub-odroid-${VERSION}"
[[ -d "${package_root}" ]]

echo IMAGE_PATCH_START
rm -rf "${MOUNT_DIR}/opt/stream-hub-device/device"
cp -a "${package_root}/device" "${MOUNT_DIR}/opt/stream-hub-device/device"
install -m 0644 "${package_root}/pyproject.toml" \
  "${MOUNT_DIR}/opt/stream-hub-device/pyproject.toml"
install -m 0644 "${package_root}/requirements-device.txt" \
  "${MOUNT_DIR}/opt/stream-hub-device/requirements-device.txt"

site_packages="$(find "${MOUNT_DIR}/opt/stream-hub-device/venv/lib" \
  -type d -path '*/site-packages' | head -1)"
[[ -n "${site_packages}" ]]
rm -rf "${site_packages}/stream_agent"
cp -a "${package_root}/device/agent/stream_agent" \
  "${site_packages}/stream_agent"

old_dist="$(find "${site_packages}" -maxdepth 1 -type d \
  -name 'stream_hub_device-*.dist-info' | head -1 || true)"
if [[ -n "${old_dist}" ]]; then
  new_dist="${site_packages}/stream_hub_device-${VERSION}.dist-info"
  if [[ "${old_dist}" != "${new_dist}" ]]; then
    rm -rf "${new_dist}"
    mv "${old_dist}" "${new_dist}"
  fi
  sed -i "s/^Version: .*/Version: ${VERSION}/" "${new_dist}/METADATA"
fi

install -m 0755 \
  "${package_root}/device/installer/firstboot/stream-hub-clone-firstboot.sh" \
  "${MOUNT_DIR}/usr/local/sbin/stream-hub-clone-firstboot"
for service in stream-hub-clone-firstboot stream-player stream-agent; do
  install -m 0644 \
    "${package_root}/device/installer/systemd/${service}.service" \
    "${MOUNT_DIR}/etc/systemd/system/${service}.service"
done
install -m 0644 \
  "${package_root}/device/installer/journald/stream-hub-storage.conf" \
  "${MOUNT_DIR}/etc/systemd/journald.conf.d/stream-hub-storage.conf"

mkdir -p "${MOUNT_DIR}/etc/systemd/system/stream-agent.service.d"
printf '[Service]\nEnvironment=STREAM_HUB_URL=%s\n' "${HUB_URL}" \
  >"${MOUNT_DIR}/etc/systemd/system/stream-agent.service.d/hub.conf"
chmod 0644 \
  "${MOUNT_DIR}/etc/systemd/system/stream-agent.service.d/hub.conf"

printf '%s\n' '{"revision": 0, "default_seconds": 20, "streams": []}' \
  >"${MOUNT_DIR}/etc/stream-hub/playlist.json"
chown 0:"$(stat -c %g "${MOUNT_DIR}/etc/stream-hub")" \
  "${MOUNT_DIR}/etc/stream-hub/playlist.json"
chmod 0660 "${MOUNT_DIR}/etc/stream-hub/playlist.json"

rm -f \
  "${MOUNT_DIR}/etc/stream-hub/device.json" \
  "${MOUNT_DIR}/etc/stream-hub/command-results.json" \
  "${MOUNT_DIR}/etc/stream-hub/agent-state.json"
rm -rf \
  "${MOUNT_DIR}/etc/stream-hub/commands" \
  "${MOUNT_DIR}/etc/stream-hub/command-results"
: >"${MOUNT_DIR}/etc/stream-hub/golden-image"
chmod 0600 "${MOUNT_DIR}/etc/stream-hub/golden-image"

rm -f "${MOUNT_DIR}/etc/ssh/ssh_host_"*
find "${MOUNT_DIR}/root" "${MOUNT_DIR}/home" -type f \
  \( -name authorized_keys -o -name authorized_keys2 -o -name known_hosts \
     -o -name .bash_history -o -name .python_history \) \
  -delete 2>/dev/null || true
find "${MOUNT_DIR}/root" "${MOUNT_DIR}/home" -type f \
  -path '*/.ssh/*' -delete 2>/dev/null || true

: >"${MOUNT_DIR}/etc/machine-id"
rm -f \
  "${MOUNT_DIR}/var/lib/dbus/machine-id" \
  "${MOUNT_DIR}/var/lib/systemd/random-seed" \
  "${MOUNT_DIR}/var/lib/tailscale/tailscaled.state" \
  "${MOUNT_DIR}/var/lib/systemd/timesync/clock"
rm -rf \
  "${MOUNT_DIR}/var/lib/cloud/instances/"* \
  "${MOUNT_DIR}/var/lib/dhcp/"* \
  "${MOUNT_DIR}/var/lib/NetworkManager/"*lease*
find "${MOUNT_DIR}/var/log" -mindepth 1 -delete 2>/dev/null || true
mkdir -p "${MOUNT_DIR}/var/log/journal"
find "${MOUNT_DIR}/tmp" "${MOUNT_DIR}/var/tmp" -mindepth 1 \
  -delete 2>/dev/null || true

password_hash="$(openssl passwd -6 -salt streamhub odroid)"
python3 - "${MOUNT_DIR}/etc/shadow" "${password_hash}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
password_hash = sys.argv[2]
rows = []
for line in path.read_text().splitlines():
    fields = line.split(":")
    if fields[0] in {"root", "odroid"}:
        fields[1] = password_hash
    rows.append(":".join(fields))
path.write_text("\n".join(rows) + "\n")
PY

sync
echo IMAGE_ZERO_FREE_SPACE
set +e
dd if=/dev/zero of="${MOUNT_DIR}/.stream-hub-zero" bs=16M status=none
set -e
rm -f "${MOUNT_DIR}/.stream-hub-zero"
sync

umount "${MOUNT_DIR}"
fsck_fix "${loop}p2"
losetup -d "${loop}"
loop=""
mv "${PARTIAL}" "${OUTPUT}"

echo IMAGE_RAW_READY
sha256sum "${OUTPUT}" | tee "${OUTPUT}.sha256"
echo IMAGE_COMPRESS_START
zstd -T0 -6 -f "${OUTPUT}" -o "${OUTPUT}.zst"
zstd -t "${OUTPUT}.zst"
sha256sum "${OUTPUT}.zst" | tee "${OUTPUT}.zst.sha256"

echo IMAGE_AUDIT_START
loop="$(losetup --find --show --partscan --read-only "${OUTPUT}")"
fsck_read_only "${loop}p2"
mount -o ro,noload "${loop}p2" "${MOUNT_DIR}"

grep -q "${VERSION}" \
  "${MOUNT_DIR}/opt/stream-hub-device/device/agent/stream_agent/__init__.py"
find "${MOUNT_DIR}/opt/stream-hub-device/venv/lib" \
  -path '*/site-packages/stream_agent/__init__.py' \
  -exec grep -q "${VERSION}" {} \;
[[ "$(cat "${MOUNT_DIR}/etc/stream-hub/playlist.json")" == \
  '{"revision": 0, "default_seconds": 20, "streams": []}' ]]
[[ -f "${MOUNT_DIR}/etc/stream-hub/golden-image" ]]
[[ ! -e "${MOUNT_DIR}/etc/stream-hub/device.json" ]]
[[ ! -e "${MOUNT_DIR}/etc/stream-hub/command-results.json" ]]
[[ ! -s "${MOUNT_DIR}/etc/machine-id" ]]
[[ -z "$(find "${MOUNT_DIR}/etc/ssh" -name 'ssh_host_*' -type f -print -quit)" ]]
[[ -z "$(find "${MOUNT_DIR}/root" "${MOUNT_DIR}/home" \
  -name authorized_keys -type f -print -quit 2>/dev/null)" ]]
grep -qx "Environment=STREAM_HUB_URL=${HUB_URL}" \
  "${MOUNT_DIR}/etc/systemd/system/stream-agent.service.d/hub.conf"

python3 - "${MOUNT_DIR}/etc/shadow" "${password_hash}" <<'PY'
from pathlib import Path
import sys

rows = {
    line.split(":")[0]: line.split(":")[1]
    for line in Path(sys.argv[1]).read_text().splitlines()
}
assert rows["root"] == sys.argv[2]
assert rows["odroid"] == sys.argv[2]
PY

forbidden_pattern='100\.125\.|192\.168\.102\.'
if [[ -n "${STREAM_HUB_IMAGE_FORBIDDEN_PATTERN:-}" ]]; then
  forbidden_pattern="${forbidden_pattern}|${STREAM_HUB_IMAGE_FORBIDDEN_PATTERN}"
fi
if grep -R -I -l -E \
  "${forbidden_pattern}" \
  "${MOUNT_DIR}/etc" \
  "${MOUNT_DIR}/opt/stream-hub-device" \
  "${MOUNT_DIR}/root" \
  "${MOUNT_DIR}/home" \
  "${MOUNT_DIR}/var/lib/cloud" 2>/dev/null | head -1 | grep -q .; then
  echo SENSITIVE_AUDIT_FAIL >&2
  exit 32
fi

[[ -x "${MOUNT_DIR}/usr/bin/ffprobe" ]]
[[ -x "${MOUNT_DIR}/usr/bin/mpv" ]]
echo IMAGE_AUDIT_OK

raw_size="$(stat -c %s "${OUTPUT}")"
compressed_size="$(stat -c %s "${OUTPUT}.zst")"
raw_sha="$(cut -d' ' -f1 "${OUTPUT}.sha256")"
compressed_sha="$(cut -d' ' -f1 "${OUTPUT}.zst.sha256")"
cat >"${OUTPUT}.metadata.txt" <<EOF
artifact=$(basename "${OUTPUT}.zst")
source_artifact=$(basename "${SOURCE_IMAGE}")
architecture=arm64
board=Odroid-C4
version=${VERSION}
raw_size_bytes=${raw_size}
raw_sha256=${raw_sha}
compressed_size_bytes=${compressed_size}
compressed_sha256=${compressed_sha}
golden_image_firstboot=enabled
hub_url=${HUB_URL}
playlist=empty-revision-0
source_identity_removed=yes
ssh_keys_removed=yes
machine_id_cleared=yes
logs_and_histories_removed=yes
default_accounts=root:odroid,odroid:odroid
filesystem_check=passed
zstd_test=passed
security_audit=passed
created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

umount "${MOUNT_DIR}"
losetup -d "${loop}"
loop=""
chmod 0644 \
  "${OUTPUT}" \
  "${OUTPUT}.zst" \
  "${OUTPUT}.sha256" \
  "${OUTPUT}.zst.sha256" \
  "${OUTPUT}.metadata.txt"
ls -lh "${OUTPUT}"*
echo ODROID_IMAGE_DONE
