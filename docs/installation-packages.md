# Bağımsız kurulum paketleri

Stream Hub iki ayrı Linux dağıtım paketi olarak üretilir:

- `stream-hub-odroid-<version>.tar.gz`: MPV player, cihaz agent'ı, systemd servisleri ve log sınırları
- `stream-hub-server-<version>.tar.gz`: Merkezi API, web arayüzü, systemd servisi, log sınırları ve SQLite yedekleri

## Paketleri üretme

Repo kökünde:

```bash
python packaging/build_packages.py
```

Arşivler ve `SHA256SUMS` dosyası `dist/` altında oluşturulur. Her arşivin içinde ayrıca paket dosyalarını doğrulayan `MANIFEST.sha256` bulunur.

## Odroid tek komut kurulumu

Arşivi Odroid'e kopyaladıktan sonra:

```bash
tar -xzf stream-hub-odroid-0.1.0.tar.gz && sudo ./stream-hub-odroid-0.1.0/install.sh
```

Player kullanıcısı `odroid` değilse:

```bash
tar -xzf stream-hub-odroid-0.1.0.tar.gz && sudo PLAYER_USER=kullanici ./stream-hub-odroid-0.1.0/install.sh
```

Installer `apt` üzerinden `ca-certificates`, `curl`, `ffmpeg`, `mpv`, Python, venv ve `sudo` paketlerini; paket içindeki sabitlenmiş Python gereksinimlerini ise izole venv içine otomatik kurar.

## Hub tek komut kurulumu

Arşivi merkezi Debian/Ubuntu sunucuya kopyaladıktan sonra:

```bash
tar -xzf stream-hub-server-0.1.0.tar.gz && sudo ./stream-hub-server-0.1.0/install.sh
```

Installer `apt` üzerinden `ca-certificates`, `curl`, `openssl`, Python ve venv paketlerini; Hub Python bağımlılıklarını ise izole venv içine otomatik kurar.

### TrueNAS SCALE

TrueNAS SCALE üzerinde host installer çalıştırılmaz. Hub arşivini açtıktan sonra Apps pool adı verilerek container deployment kullanılır:

```bash
sudo python3 hub/container/deploy_truenas.py --pool SENG
```

Bu komut Hub image'ını oluşturur, `<pool>/stream-hub` kalıcı dataset'ini hazırlar ve Hub'ı TrueNAS Apps içinde `stream-hub` adlı Custom App olarak oluşturur veya günceller. Hub, günlük backup ve mDNS ilanı ayrı container'larda çalışır.

## Veri koruma ve doğrulama

- Odroid yeniden kurulumunda playlist ve cihaz kimliği korunur.
- Hub yeniden kurulumunda yönetici hesabı, ayarlar ve SQLite veritabanı korunur.
- Her iki installer systemd servislerini etkinleştirir ve kurulum sonunda health endpoint'ini kontrol eder.
- Hub installer ayrıca web arayüzünü ve günlük SQLite backup timer'ını doğrular.
- Paketler şu anda Debian/Ubuntu tabanlı systemd sistemlerini hedefler.
