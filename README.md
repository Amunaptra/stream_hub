# Stream Hub

Stream Hub, ağdaki Odroid tabanlı HLS, RTMP, RTSP ve UDP/RTP multicast yayın oynatıcılarını merkezi bir web panelinden keşfetmek, izlemek ve yönetmek için geliştirilen sistemdir.

> **Durum: v0.1.7 saha doğrulamalı kararlı sürüm**
>
> Odroid C4, Ubuntu 22.04/aarch64 ve TrueNAS SCALE üzerinde gerçek cihazlarla
> kurulum, golden-image klonlama, merkezi config, reboot ve yayın oynatma
> akışları doğrulandı. 13 cihazlık canlı filoda tek kalıcı MPV süreci ve IPC
> `loadfile replace` ile siyah ekransız yayın geçişi devreye alındı. v0.1.2 ile
> HLS yanında RTMP/RTMPS config, kaynak ön kontrolü ve sağlık ölçümü canlıda
> doğrulandı. v0.1.7 ile UDP/RTP multicast oynatma, ortak yayın kütüphanesi,
> TXT/JSON toplu içe aktarma, arama ve toplu silme tamamlandı. Canlı Hub 13
> cihazlık filoda ve 42 kayıtlı yayın kaynağıyla doğrulandı.

Sistem 15 Odroid cihazını merkezi olarak yönetmek üzere tasarlanmıştır. Cihazlar Hub olmasa da son geçerli oynatma listesiyle bağımsız çalışmaya devam eder.

## Bileşenler

- `device/agent`: Sürümlü cihaz API'si, güvenli config ve sağlık telemetrisi
- `device/player`: Hub'dan bağımsız HLS/RTMP/RTSP/UDP/RTP oynatma döngüsü
- `device/installer`: Veri korumalı Odroid kurulumu, systemd ve journal sınırları
- `hub/backend`: Cihaz envanteri, heartbeat, komut ve config yönetimi
- `hub/ui`: Merkezi yönetim paneli
- `tests`: Cihaz modelleri, depolama ve API doğrulama testleri

## Güncel durum

Cihaz çalışma katmanı, mDNS/sabit URL discovery, heartbeat, Hub cihaz envanteri,
cihaz isimlendirme, merkezi config senkronizasyonu, reboot/player-restart komut
kuyruğu, yayın sağlık kontrolü ve merkezi web arayüzü tamamlandı. Her cihazın
oynatma listesi en fazla 50 yayın bağlantısını destekler.
Yayın adresleri `http://`, `https://`, `rtmp://`, `rtmps://`, `rtsp://`,
`rtsps://`, `udp://` ve `rtp://` protokollerini kabul eder. UDP/RTP hedefleri
yalnız `224.0.0.0/4` IPv4 multicast aralığı ve açık bir UDP portuyla kabul
edilir. HLS sağlığı manifest içeriğiyle; RTMP, RTSP, UDP ve RTP sağlığı
`ffprobe` ile ölçülür. RTSP ön kontrolünde routed ağlarda daha kararlı
davranması için TCP taşıması kullanılır.

Hub yayın kütüphanesi cihaz playlist'lerinden bağımsızdır. TXT veya JSON
dosyasından en fazla 500 kayıt tek işlemde içe aktarılabilir; kayıtlar ID ya da
URL ile aranabilir, toplu seçilip silinebilir. Kütüphaneden bir cihaza eklenen
kaynaklar başlangıçta devre dışıdır ve operatör açıkça **Kaydet ve gönder**
demeden cihaz config'i değişmez.

Sahada doğrulanan başlıca akışlar:

- Ubuntu Minimal üzerine tek komut Odroid kurulumu;
- TrueNAS SCALE üzerine Hub kurulumu ve kalıcı SQLite verisi;
- farklı routed subnet'lerden sabit Hub URL ile heartbeat;
- benzersiz kimlik üreten ve root filesystem'i büyüten golden-image klonlama;
- Hub'dan playlist gönderimi, player restart ve cihaz reboot;
- yayınlar arasında SDL penceresini kapatmayan kalıcı MPV ve IPC tabanlı temiz
  geçiş;
- yedi gün/1 GB ile sınırlandırılmış cihaz logları;
- cihaz ve yayın sağlık bilgilerinin web arayüzünde izlenmesi.
- ortak yayın kütüphanesi, dosyadan toplu içe aktarma, arama ve toplu silme;
- MPEG-TS/UDP ve RTP multicast kaynaklarının düşük gecikmeli oynatılması.

Kararlı saha sürümü ayrıntıları için
[v0.1.7 release notlarına](docs/releases/v0.1.7.md), multicast altyapısı için
[v0.1.6](docs/releases/v0.1.6.md) ve önceki RTSP/watchdog kabulü için
[v0.1.4](docs/releases/v0.1.4.md) notlarına bakın.

Yerel doğrulama:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest
```

Odroid kurulum bilgisi için [device/README.md](device/README.md), cihaz API sözleşmesi için [docs/device-api-v1.md](docs/device-api-v1.md), keşif akışı için [docs/discovery-and-heartbeat.md](docs/discovery-and-heartbeat.md), merkezi komut akışı için [docs/central-management.md](docs/central-management.md) dosyasına bakın.

Bağımsız Odroid ve Hub dağıtım arşivlerini üretme ve tek komutla kurma bilgisi için [docs/installation-packages.md](docs/installation-packages.md) dosyasına bakın.

Klon güvenli golden-image üretimi için [docs/golden-image.md](docs/golden-image.md)
dosyasına bakın. Canlı cihazdan alınmış özel disk imajları kimlik bilgileri
içerebileceği için dağıtılmaz. v0.1.7 GitHub Release içinde ayrıca özel
kimlikleri temizlenmiş ve default hesaplara döndürülmüş public Odroid C4 imajı
bulunur. Bu imaj HLS, RTMP/RTMPS, RTSP/RTSPS, UDP/RTP multicast, siyah ekransız
geçiş ve otomatik donma/reconnect watchdog özelliklerini birlikte içerir.

Proje kararları ve public ilerleme kayıtları için [stream_hub_change_log.md](stream_hub_change_log.md) dosyasına bakın.
