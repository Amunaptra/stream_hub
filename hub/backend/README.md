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
