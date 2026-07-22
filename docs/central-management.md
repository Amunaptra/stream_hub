# Merkezi config ve komut yönetimi

## Config senkronizasyonu

Hub her cihaz için iki ayrı durumu izler:

- `config_revision`: Cihazın heartbeat ile uyguladığını bildirdiği revision
- `desired_revision`: Hub kullanıcısının cihaza göndermek istediği revision

Hub'da playlist kaydedildiğinde revision otomatik artırılır ve durum `pending` olur. Sonraki heartbeat yanıtında config cihaza gönderilir. Cihaz config'i doğrular, atomik kaydeder ve player servisini yeniden başlatır.

Sonuç durumları:

- `pending`: Gönderilmeyi bekliyor
- `delivered`: Heartbeat yanıtıyla cihaza gönderildi
- `applied`: Cihaz başarıyla uyguladığını bildirdi
- `failed`: Cihaz uygulayamadı ve önceki config'e döndü

## Komut kuyruğu

İlk sürüm iki merkezi komutu destekler:

- `player_restart`
- `reboot`

Komutlar yalnızca onaylı cihazlar için kuyruğa alınır. Cihaz komutları heartbeat yanıtında alır, yerel sınırlı sistem kontrolüyle çalıştırır ve sonucu Hub'a bildirir.

Teslim cevabı ağda kaybolursa Hub tamamlanmamış komutu yeniden gönderir. Cihaz son 100 komut sonucunu kalıcı olarak sakladığı için aynı komut kimliği ikinci kez çalıştırılmaz; önceki sonuç tekrar Hub'a bildirilir.

## Hub yönetim endpoint'leri

```text
PUT  /api/v1/devices/{device_id}/config
POST /api/v1/devices/{device_id}/commands
GET  /api/v1/devices/{device_id}/commands
```

Bu endpoint'ler Hub admin Bearer token gerektirir. Config ve komut sonuçlarını bildiren cihaz endpoint'leri ise ilgili cihazın benzersiz token'ını doğrular.
