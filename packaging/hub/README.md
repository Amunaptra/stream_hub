# Stream Hub merkezi sunucu paketi

Bu paket merkezi Hub API'sini, web arayüzünü, systemd servisini, sınırlı journal politikasını ve günlük SQLite yedeklemesini kurar.

## Kurulum

```bash
sudo ./install.sh
```

Kurulum mevcut `/etc/stream-hub/hub.env`, yönetici token'ı ve `/var/lib/stream-hub/hub.sqlite3` veritabanını korur. Kurulum sonunda Hub servisi, `healthz` ve web arayüzü doğrulanır.

Panel adresi ve yönetici token'ını okuma komutu installer sonunda yazdırılır.
