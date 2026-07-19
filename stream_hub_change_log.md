# Stream Hub Change Log

Bu dosya Stream Hub projesindeki mimari kararları, uygulama değişikliklerini ve doğrulama sonuçlarını kronolojik olarak kaydeder.

## Kayıt kuralları

- Her değişiklik tarih, kapsam ve doğrulama bilgisiyle kaydedilir.
- Cihaz tarafı, Hub tarafı ve kurulum değişiklikleri ayrı başlıklarla belirtilir.
- Tamamlanmamış işler açıkça `Planlandı` veya `Devam ediyor` olarak işaretlenir.
- Dağıtılan sürümlerde cihaz ve Hub sürüm numaraları kayda eklenir.
- Tamamlanan her geliştirme, düzeltme, test, doğrulama ve dağıtım adımı aynı çalışma içinde bu dosyaya eklenir.
- Change log kaydı yazılmadan ilgili iş tamamlanmış kabul edilmez.

## 2026-07-19 - Proje başlangıcı

### Durum

Planlandı.

### Hedef

15 adet Odroid yayın cihazını tek bir merkezi Hub üzerinden keşfetmek, izlemek ve yönetmek.

### İlk aşama kapsamı

- Odroid cihazların ağ üzerinde otomatik keşfedilmesi ve Hub'a kaydolması.
- Her cihazın kalıcı ve IP adresinden bağımsız bir cihaz kimliğine sahip olması.
- Cihazların online/offline, player, aktif yayın ve sistem sağlık durumlarının listelenmesi.
- Her cihazın oynatma listesinin ayrı ayrı düzenlenmesi, kaydedilmesi ve cihaza gönderilmesi.
- Yapılandırma gönderiminin revision ve doğrulama sonucu ile takip edilmesi.
- Hub üzerinden player restart ve cihaz reboot işlemlerinin yapılması.
- Hub erişilemezken cihazların son geçerli yapılandırmayla yayın oynatmaya devam etmesi.

### Cihaz depolama ve log gereksinimleri

- Hedef cihazlarda 16 GB eMMC bulunur.
- Cihaz logları en fazla 7 gün saklanır.
- Cihaz üzerindeki uygulama ve sistem loglarının toplam kullanımı 1 GB'ı geçmez.
- Log sistemi diskte en az 2 GB boş alan bırakacak şekilde sınırlandırılır.
- Sürekli hata üreten servislerin diski doldurmasını önlemek için rate limit uygulanır.
- MPV ve agent çıktıları sınırsız büyüyen doğrudan dosyalara yazılmaz.
- Hub üzerinde disk, boş alan ve log kullanımı için uyarı/kritik durumları gösterilir.

### Mimari kararlar

- Önce tek cihazdaki player ve agent katmanı güvenilir hale getirilecek.
- Player, Hub'dan bağımsız çalışabilecek ve son geçerli config'i kullanacak.
- Hub ile cihaz arasındaki API `/api/v1` altında sürümlenecek.
- Cihaz kimliği IP adresi değil, kurulum sırasında oluşturulan kalıcı UUID olacak.
- Hub, istenen config ile cihazın uyguladığını bildirdiği config revision'ını ayrı tutacak.
- Otomatik keşif için yerel ağ discovery ve cihaz heartbeat mekanizması birlikte kullanılacak.
- Mevcut monolitik `setup.sh`, kaynak kod ile kurulum mantığını ayıracak şekilde yeniden düzenlenecek.
- Cihaz başına benzersiz kimlik doğrulama anahtarı kullanılacak; ortak varsayılan token kullanılmayacak.

### Bilinen başlangıç sorunları

- Eski setup dosyasında Windows CRLF satır sonları bulunuyor.
- Paket listesinde gereksiz/hatalı bağımsız `nmcli` paketi bulunuyor.
- Player durum dosyası üretiminde geçersiz Bash parameter expansion kullanılıyor.
- Screenshot dizini player kullanıcısı tarafından yazılabilir değil.
- Root çalışan API'de `shell=True` komut enjeksiyonu riski bulunuyor.
- Setup tekrar çalıştırıldığında kullanıcı ve yayın yapılandırmasını sıfırlıyor.
- Oturum token formatı binary ayraç nedeniyle rastlantısal doğrulama hatası üretebiliyor.

### Sonraki çalışma

1. Repo dizin yapısını oluşturmak.
2. Cihaz API sözleşmesini ve veri modellerini tanımlamak.
3. Player ve agent kaynaklarını setup dosyasından ayırmak.
4. Log ve depolama korumasını cihaz katmanına eklemek.
5. Tek Odroid üzerinde kurulum ve oynatma doğrulaması yapmak.
6. Hub cihaz envanteri ve heartbeat ekranını geliştirmek.

## 2026-07-19 - Cihaz çekirdeği 0.1.0

### Durum

Tamamlandı; gerçek Odroid kurulumu henüz yapılmadı.

### Eklenenler

- Kaynak kod ve installer birbirinden ayrıldı.
- `/api/v1` altında token korumalı cihaz API'si oluşturuldu.
- Kurulum sırasında kalıcı UUID ve cihaz başına benzersiz token üretimi eklendi.
- Playlist için Pydantic doğrulaması, en fazla 40 yayın ve benzersiz stream ID kontrolü eklendi.
- Config revision, idempotent tekrar gönderim, atomik kayıt ve önceki config yedeği eklendi.
- Player restart başarısız olduğunda önceki config'e otomatik dönüş eklendi.
- MPV komutları shell kullanmadan argüman listesiyle çalıştırıldı.
- Player logları doğrudan dosyaya yazmak yerine journald'a yönlendirildi.
- Journald için 7 gün, toplam 1 GB, 2 GB boş alan ve 64 MB journal parçası sınırları eklendi.
- Agent root yerine sınırlı `stream-agent` hesabıyla çalışacak şekilde tasarlandı.
- Player restart ve reboot için dar kapsamlı sudoers kuralları eklendi.
- CPU, RAM, disk, boş alan, log kullanımı, sıcaklık, uptime ve player state telemetrisi eklendi.
- HLS sağlık kontrolü yalnızca kayıtlı yayınlar üzerinde ve sınırlı cevap okuyarak çalışacak şekilde eklendi.
- Installer tekrar çalıştırıldığında playlist ve cihaz verilerini koruyacak şekilde hazırlandı.
- Python bağımlılıkları kontrollü sürüm dosyasına bağlandı.
- Linux kurulum güvenliği için shell, systemd, Python, TOML ve metin dosyalarında LF satır sonu repo politikası genişletildi.

### Doğrulama

- 17 otomatik test başarılı.
- Python kaynakları compile kontrolünden geçti.
- Git diff whitespace kontrolü başarılı.
- Kaynak, systemd ve installer dosyalarında CRLF bulunmadığı doğrulandı.
- Windows ortamında yerel Bash bulunmadığı için `bash -n` ve gerçek systemd doğrulaması yapılamadı.
- Cihaz çekirdeği `agent/device-core` dalında GitHub'a gönderildi.
- İlk push çağrılarında yerel istemci zaman aşımı yaşandı; GitHub dalının oluştuğu API ile doğrulandı ve Git credential yapılandırması yenilenerek dal takibi başarıyla tamamlandı.
- GitHub üzerinde cihaz çekirdeği incelemesi için draft PR `#1` açıldı.

### Sonraki çalışma

1. Installer'ı tek Odroid üzerinde dry-run ve gerçek kurulumla doğrulamak.
2. mDNS Hub discovery ve cihaz heartbeat protokolünü eklemek.
3. Hub backend cihaz envanteri ve durum veritabanını oluşturmak.
4. İlk merkezi cihaz listesi ekranını hazırlamak.
