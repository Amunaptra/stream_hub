# Discovery ve heartbeat

## Keşif

Hub aynı yerel ağda `_stream-hub._tcp.local.` mDNS servisini ilan eder. Odroid agent sabit `STREAM_HUB_URL` tanımlanmamışsa bu ilanı dinler ve Hub API adresini otomatik bulur.

Sabit adres her zaman önceliklidir:

```bash
STREAM_HUB_URL=http://192.168.1.10:8788
```

mDNS multicast paketleri farklı VLAN veya subnet'lere varsayılan olarak geçmez. Böyle ortamlarda DNS adı, sabit Hub URL veya ağ seviyesinde mDNS reflector gerekir.

## Heartbeat

Cihaz varsayılan olarak her 10 saniyede aşağıdaki bilgileri gönderir:

- Kalıcı cihaz kimliği ve hostname
- Agent sürümü ve API portu
- IP adresleri
- Player servis ve aktif yayın durumu
- Uygulanan config revision
- CPU, RAM, disk ve boş alan
- Yerel journal kullanımı
- Sıcaklık ve uptime

Hub 30 saniye heartbeat alamazsa cihazı offline olarak işaretler. Cihaz Hub bağlantısı kesildiğinde yerel playlist ile yayın oynatmaya devam eder.

## İlk kayıt ve güven modeli

Her cihaz benzersiz Bearer token ile heartbeat gönderir. Hub ilk gördüğü cihaz kimliği/token eşleşmesini kaydeder ve cihazı `pending` durumuna alır. Kullanıcı cihazı Hub üzerinden onaylayana kadar merkezi config veya reboot komutu verilemez.

Hub token'ın kendisini değil SHA-256 özetini saklar. Aynı cihaz kimliği daha sonra farklı token ile kullanılmaya çalışılırsa istek reddedilir.

Bu ilk sürüm güvenilen yerel ağ içindir. HTTP trafiğinin dinlenebildiği ağlarda token aktarımını korumak için sonraki güvenlik aşamasında HTTPS veya karşılıklı TLS kullanılmalıdır.
