# Device runtime

Bu dizin Odroid üzerinde çalışan iki bağımsız servisi içerir:

- `stream-player.service`: Yerel playlist'i MPV ile oynatır.
- `stream-agent.service`: Hub için sürümlü ve token korumalı cihaz API'sini sunar.

Player, Hub veya agent erişilemezken son geçerli `/etc/stream-hub/playlist.json` dosyasıyla çalışmaya devam eder.

Playlist yayınları HLS için `http://`/`https://`, RTMP için
`rtmp://`/`rtmps://` adreslerini destekler. RTMP kaynak ön kontrolü ve sağlık
ölçümü kurulumla gelen `ffprobe` üzerinden yapılır.

## Kurulum

Desteklenen ilk hedef Debian/Ubuntu tabanlı Odroid sistemidir. Mevcut playlist ve cihaz verileri tekrar kurulumda korunur.

```bash
sudo ./device/installer/install.sh
```

Farklı bir mevcut player kullanıcısı için:

```bash
sudo PLAYER_USER=myplayer ./device/installer/install.sh
```

## Log ve depolama

Player ve agent doğrudan büyüyen log dosyaları oluşturmaz. Çıktılar journald tarafından yönetilir:

- En fazla 7 gün
- Toplam en fazla 1 GB
- Diskte en az 2 GB boş alan
- Journal parçası başına en fazla 64 MB

Player logları:

```bash
journalctl -u stream-player.service
```

Agent logları:

```bash
journalctl -u stream-agent.service
```
