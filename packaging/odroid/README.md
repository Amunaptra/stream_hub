# Stream Hub Odroid paketi

Bu paket Odroid cihazına yayın oynatıcıyı, cihaz agent'ını, systemd servislerini ve sınırlı journal politikasını kurar.

## Kurulum

```bash
sudo ./install.sh
```

Varsayılan HDMI kullanıcısı `odroid` olmalıdır. Farklı bir kullanıcı gerekiyorsa:

```bash
sudo PLAYER_USER=kullanici_adi ./install.sh
```

Kurulum mevcut `/etc/stream-hub/playlist.json` ve cihaz kimliğini korur. Kurulum sonunda `stream-player.service`, `stream-agent.service` ve `http://127.0.0.1:8787/healthz` doğrulanır.
