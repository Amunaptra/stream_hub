# TrueNAS SCALE container deployment

Hub, TrueNAS SCALE 24.10 ve sonrasında Custom App / Docker Compose olarak çalıştırılabilir.

- Hub container host network kullanır; böylece `8788/tcp` doğrudan yerel ağa açılır.
- TrueNAS'ın mevcut Avahi servisiyle `5353/UDP` çakışmaması için mDNS ilanı, host D-Bus soketine bağlanan ayrı `mdns` sidecar tarafından yapılır.
- SQLite verisi `/data`, günlük yedekler `/backups` mount'unda tutulur.
- Backup sidecar SQLite online backup API'sini kullanır ve en fazla 7 günlük/7 dosyalık yedek saklar.
- Her container için Docker JSON logları 10 MB x 7 dosyayla sınırlandırılır.
- Hub root olmayan `568:568` TrueNAS Apps kullanıcısıyla çalışır.

Image oluşturma:

```bash
docker build -f hub/container/Dockerfile -t stream-hub:0.1.0 .
```

`compose.truenas.yml` dosyası çalıştırılmadan önce şu değişkenleri gerektirir:

- `STREAM_HUB_ADMIN_USERNAME`
- `STREAM_HUB_ADMIN_PASSWORD`
- `STREAM_HUB_DATA_PATH`
- `STREAM_HUB_BACKUP_PATH`

TrueNAS web arayüzünde Apps > Discover Apps > Install via YAML kullanılarak aynı Compose tanımı Custom App olarak kurulabilir.

Repo kaynakları TrueNAS üzerinde bulunduğunda otomatik deployment:

```bash
sudo python3 hub/container/deploy_truenas.py --pool SENG
```

Bu komut `SENG/stream-hub` dataset'ini, kalıcı veri/yedek dizinlerini ve ilk yönetici giriş bilgilerini mevcutsa korur; image'ı yeniden oluşturur ve Custom App'i oluşturur veya günceller. İlk kullanıcı adı ve parola root-only `deployment/admin-username` ve `deployment/admin-password` dosyalarından okunabilir. Daha sonra giriş bilgileri paneldeki **Hesap** düğmesinden değiştirilir; parola SQLite içinde salt'lı `scrypt` özeti olarak saklanır.
