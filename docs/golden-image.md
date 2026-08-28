# Odroid golden image

This procedure creates a full-disk, clone-safe image of a configured Odroid.
The source device remains registered and usable after capture.

## Security warning

A full-disk capture is not automatically safe to publish. Even though the
first-boot service replaces clone identity data during boot, the image file
itself can still contain:

- the source device token and registration file;
- password hashes from `/etc/shadow`;
- SSH host and authorized keys;
- network configuration, logs, and shell history.

Keep operational images in access-controlled storage. Do not upload a live
capture to a public repository or release. A separately sanitized public image
must remove every deployment-specific credential and pass a dedicated security
audit before distribution.

The v0.1.2 public release image is a separate sanitized derivative. It is not
the private field image. Its device token, command cache, authorized keys, SSH
host keys, machine ID, logs, histories, leases, and deleted free-space data
were cleared before release.

The v0.1.2 image supports HLS over HTTP/HTTPS and RTMP/RTMPS. RTMP source
preflight and stream-health checks use the bundled `ffprobe` runtime before
the persistent MPV process replaces the current stream.

Default public-image accounts:

- `root` / `odroid`
- `odroid` / `odroid`

Change both passwords immediately after first boot. The public image is
preconfigured for Hub URL `http://192.168.100.142:8788`; deployments using a
different address must replace
`/etc/systemd/system/stream-agent.service.d/hub.conf`.

## What changes on the first boot of a clone

When `/etc/stream-hub/golden-image` exists, the first-boot service runs before
SSH, the player, and the agent. It:

- derives a unique hostname from the device MAC address;
- generates a new machine ID and SSH host keys;
- clears the copied random seed and stale network leases;
- removes the source device registration and command results;
- expands the root partition and filesystem to fill the target eMMC;
- removes the image-capture public key, deletes the marker, and reboots.

After the automatic reboot, the agent creates a unique device identity and
registers with the configured hub. The playlist remains available as the
initial template.

## Capture

1. Install the current Odroid package.
2. Stop `stream-agent.service` and `stream-player.service`.
3. Create `/etc/stream-hub/golden-image`.
4. Flush writes and freeze `/` while reading the complete eMMC block device.
5. Compress the stream on the storage server, calculate SHA-256, and save
   metadata beside the image.
6. Unfreeze `/`, remove the marker from the source, and restart both services.

Never reboot the source while the marker exists. A capture workflow must use a
trap so `/` is unfrozen even when the image transfer fails.

## Restore

Write the decompressed image to an eMMC that is at least as large as the source:

```bash
zstd -dc stream-hub-odroid-c4-YYYYMMDD.img.zst | sudo dd of=/dev/DEVICE bs=4M status=progress conv=fsync
```

Verify the target device path carefully. The first clone boot intentionally
reboots once; it becomes visible in the hub after the second boot.
