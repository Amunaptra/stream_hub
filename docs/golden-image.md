# Odroid golden image

This procedure creates a full-disk, clone-safe image of a configured Odroid.
The source device remains registered and usable after capture.

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
