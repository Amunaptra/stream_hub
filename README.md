# Stream Hub

Stream Hub, ağdaki Odroid tabanlı HLS yayın oynatıcılarını merkezi bir web panelinden keşfetmek, izlemek ve yönetmek için geliştirilen sistemdir.

Projenin ilk hedefi 15 cihazı destekleyen bir MVP oluşturmaktır. Cihazlar Hub olmasa da son geçerli oynatma listesiyle bağımsız çalışmaya devam eder.

## Bileşenler

- `device/agent`: Sürümlü cihaz API'si, güvenli config ve sağlık telemetrisi
- `device/player`: Hub'dan bağımsız HLS oynatma döngüsü
- `device/installer`: Veri korumalı Odroid kurulumu, systemd ve journal sınırları
- `hub/backend`: Cihaz envanteri, heartbeat, komut ve config yönetimi
- `hub/ui`: Merkezi yönetim paneli
- `tests`: Cihaz modelleri, depolama ve API doğrulama testleri

## Güncel durum

Cihaz çalışma katmanının ilk sürümü ile mDNS discovery, heartbeat ve Hub cihaz envanteri tamamlandı. Merkezi config/komut kuyruğu ve web arayüzü sıradaki geliştirme aşamasıdır.

Yerel doğrulama:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest
```

Odroid kurulum bilgisi için [device/README.md](device/README.md), cihaz API sözleşmesi için [docs/device-api-v1.md](docs/device-api-v1.md), keşif akışı için [docs/discovery-and-heartbeat.md](docs/discovery-and-heartbeat.md) dosyasına bakın.

Proje kararları ve ilerleme kayıtları için [stream_hub_change_log.md](stream_hub_change_log.md) dosyasına bakın.
