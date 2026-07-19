# Stream Hub

Stream Hub, ağdaki Odroid tabanlı HLS yayın oynatıcılarını merkezi bir web panelinden keşfetmek, izlemek ve yönetmek için geliştirilen sistemdir.

Projenin ilk hedefi 15 cihazı destekleyen bir MVP oluşturmaktır. Cihazlar Hub olmasa da son geçerli oynatma listesiyle bağımsız çalışmaya devam eder.

## Planlanan bileşenler

- `device/agent`: Hub iletişimi, cihaz API'si ve sağlık telemetrisi
- `device/player`: HLS oynatma döngüsü ve yerel çalışma durumu
- `device/installer`: Odroid kurulum ve systemd tanımları
- `hub/backend`: Cihaz envanteri, heartbeat, komut ve config yönetimi
- `hub/ui`: Merkezi yönetim paneli
- `shared`: Ortak API modelleri ve protokol tanımları
- `tests`: Cihaz ve Hub doğrulama testleri

Proje kararları ve ilerleme kayıtları için [stream_hub_change_log.md](stream_hub_change_log.md) dosyasına bakın.

