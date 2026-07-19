# Device API v1

Odroid agent varsayılan olarak TCP `8787` portunda çalışır. `/healthz` dışındaki bütün cihaz endpoint'leri benzersiz cihaz token'ı gerektirir.

```http
Authorization: Bearer <device-token>
```

Token ilk kurulumda `/etc/stream-hub/device.json` içinde oluşturulur. Hub pairing aşaması tamamlandığında token kullanıcı tarafından elle taşınmadan güvenli biçimde Hub'a kaydedilecektir.

## Endpoint'ler

| Metot | Yol | Amaç |
|---|---|---|
| `GET` | `/healthz` | Servisin HTTP cevap verdiğini kontrol eder |
| `GET` | `/api/v1/info` | Kalıcı cihaz kimliği, sürüm ve yetenekleri döndürür |
| `GET` | `/api/v1/status` | Player ve sistem sağlık telemetrisini döndürür |
| `GET` | `/api/v1/config` | Cihazın uyguladığı playlist revision'ını döndürür |
| `PUT` | `/api/v1/config` | Yeni playlist'i doğrular, kaydeder ve player'ı yeniden başlatır |
| `GET` | `/api/v1/streams/health` | Aktif playlist yayınlarını HLS manifest seviyesinde kontrol eder |
| `POST` | `/api/v1/player/restart` | Player servisini yeniden başlatır |
| `POST` | `/api/v1/system/reboot` | Açık onayla cihaz reboot işlemini başlatır |
| `GET` | `/api/v1/logs` | Player journal kayıtlarının sınırlı son bölümünü döndürür |

## Config revision kuralları

- Hub her içerik değişikliğinde revision değerini artırır.
- Daha eski revision `409 Conflict` ile reddedilir.
- Aynı revision ve aynı içerik idempotent başarı sayılır; player tekrar başlatılmaz.
- Aynı revision ile farklı içerik `409 Conflict` ile reddedilir.
- Config atomik olarak yazılır ve önceki geçerli sürüm yedeklenir.
- Player restart komutu başarısız olursa önceki config geri yüklenir.

Örnek config:

```json
{
  "revision": 12,
  "default_seconds": 20,
  "streams": [
    {
      "id": "salon-1",
      "enabled": true,
      "seconds": 60,
      "url": "http://media.local/salon-1/index.m3u8"
    }
  ]
}
```

`seconds=0`, yayının MPV kapanana veya yayın kopana kadar oynatılmasını ifade eder.
