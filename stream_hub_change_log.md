# Stream Hub Change Log

Bu dosya Stream Hub projesindeki mimari kararları, uygulama değişikliklerini ve doğrulama sonuçlarını kronolojik olarak kaydeder.

## Kayıt kuralları

- Her değişiklik tarih, kapsam ve doğrulama bilgisiyle kaydedilir.
- Cihaz tarafı, Hub tarafı ve kurulum değişiklikleri ayrı başlıklarla belirtilir.
- Tamamlanmamış işler açıkça `Planlandı` veya `Devam ediyor` olarak işaretlenir.
- Dağıtılan sürümlerde cihaz ve Hub sürüm numaraları kayda eklenir.

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

