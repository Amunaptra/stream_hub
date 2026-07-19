# Hub backend

Bu ilk backend paketi mDNS ile kendisini yerel ağda ilan eder ve Odroid heartbeat kayıtlarını SQLite envanterinde tutar.

Yeni bulunan cihazlar otomatik olarak envantere girer ancak başlangıçta `approved=false` durumundadır. Merkezi config ve reboot komutları yalnızca kullanıcı tarafından onaylanan cihazlara gönderilecektir.

## Yerel çalıştırma

```bash
export STREAM_HUB_ADMIN_TOKEN="uzun-ve-rastgele-bir-admin-token"
export STREAM_HUB_DATABASE="./hub.sqlite3"
uvicorn stream_hub_backend.main:APP --host 0.0.0.0 --port 8788 --no-access-log
```

Hub varsayılan olarak `_stream-hub._tcp.local.` servisini ilan eder. Test veya mDNS bulunmayan ortamda `STREAM_HUB_MDNS=0` kullanılabilir.

## Web arayüzü

Backend `hub/ui` dizinini `/ui/` altında sunar. Tarayıcı girişinde `STREAM_HUB_ADMIN_TOKEN` değeri kullanılır; doğrulama sonrasında token tarayıcıda saklanmaz ve 12 saat geçerli imzalı HttpOnly cookie oluşturulur.

```text
http://HUB-IP:8788/ui/
```

Dashboard şu ilk aşama işlevlerini içerir:

- Online, offline, pending ve sorunlu cihaz listesi
- CPU, RAM, disk, sıcaklık, log kullanımı ve uptime
- Cihaz onayı
- Cihazın reported veya desired playlist'ini düzenleme
- Config'i yeni revision ile kaydetme ve gönderme
- Player restart ve cihaz reboot komutları

## Hub kurulumu

Debian/Ubuntu tabanlı kalıcı Hub makinesinde repo kökünden:

```bash
sudo ./hub/installer/install.sh
```

Installer uygulamayı `/opt/stream-hub`, veritabanını `/var/lib/stream-hub` ve yönetici ayarlarını `/etc/stream-hub/hub.env` altında tutar. Tekrar kurulumda veritabanı ve admin token korunur.

SQLite veritabanı her gün `/var/backups/stream-hub` altına tutarlı backup API'siyle yedeklenir. En fazla 7 günlük/7 adet yedek tutulur.
