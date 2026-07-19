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

## 2026-07-19 - Discovery, heartbeat ve Hub envanteri 0.1.0

### Durum

Otomatik testlerle tamamlandı; canlı ağ ve Odroid testi kullanıcıda uygun test ortamı bulunmadığı için ertelendi.

### Eklenenler

- Hub için `_stream-hub._tcp.local.` mDNS ilanı eklendi.
- Odroid agent'a otomatik Hub keşfi ve ayarlanabilir sabit Hub URL fallback'i eklendi.
- Cihazların varsayılan 10 saniye aralıkla sistem ve player telemetrisi göndermesi sağlandı.
- Heartbeat hata logları yalnızca hata durumu değiştiğinde yazılarak log fırtınası önlendi.
- Hub backend için ayrı Python paketi ve çalışma ayarları oluşturuldu.
- 15 cihazlık ilk hedef için WAL modunda SQLite cihaz envanteri eklendi.
- İlk heartbeat ile cihazın otomatik olarak `pending` durumda kaydolması sağlandı.
- Yeni cihazların merkezi komut alabilmesi için açık Hub onay akışı eklendi.
- Cihaz token'ları Hub veritabanında düz metin yerine SHA-256 özet olarak saklandı.
- Aynı cihaz kimliğiyle farklı token gönderilmesi reddedildi.
- Hub yönetim API'leri en az 24 karakterli ayrı admin token ile korundu.
- Heartbeat içindeki üst ve alt cihaz kimliklerinin eşleşmesi zorunlu hale getirildi.
- Son heartbeat 30 saniyeyi geçtiğinde cihazın offline görünmesi eklendi.
- mDNS kullanılamadığında Hub'ın kapanmaması ve API'nin çalışmaya devam etmesi sağlandı.

### Doğrulama

- Toplam 24 otomatik test başarılı.
- Cihazdan Hub'a heartbeat gövdesi ve benzersiz Bearer token gönderimi simüle edildi.
- Otomatik pending kayıt, cihaz onayı, yanlış token reddi ve offline zaman aşımı test edildi.
- Python compile, whitespace ve LF satır sonu kontrolleri başarılı.
- FastAPI TestClient bağımlılığından gelen bir deprecation uyarısı bulunuyor; test sonuçlarını etkilemiyor.
- Gerçek multicast/mDNS, Odroid systemd ve MPV davranışı henüz canlı donanımda doğrulanmadı.
- Discovery ve Hub envanteri `agent/hub-discovery` dalına gönderildi ve draft PR `#2` açıldı; PR tabanı bağımlı cihaz çekirdeği dalıdır.

### Sonraki çalışma

1. Hub desired config ve cihaz reported config revision yönetimini eklemek.
2. Onaylı cihazlara config, player restart ve reboot komut kuyruğu eklemek.
3. Komut sonucu/ack mekanizmasını tamamlamak.
4. Merkezi cihaz listesi web arayüzünü oluşturmak.

## 2026-07-19 - Merkezi config ve komut kuyruğu 0.1.0

### Durum

Otomatik ve simüle uçtan uca testlerle tamamlandı; gerçek cihaz uygulaması bekliyor.

### Eklenenler

- Hub üzerinde her cihaz için desired config ve cihazın bildirdiği reported revision ayrıldı.
- Playlist içerik değişikliklerinde revision değerinin Hub tarafından otomatik artırılması eklendi.
- Onaylanmamış cihaza config veya sistem komutu verilmesi engellendi.
- Desired config heartbeat yanıtıyla onaylı cihaza teslim edildi.
- Cihazın config'i atomik uygulaması, player restart yapması ve sonucu Hub'a bildirmesi eklendi.
- Config uygulaması başarısız olduğunda cihazın önceki playlist'e dönmesi ve Hub'ın durumu `failed` olarak kaydetmesi sağlandı.
- Hub envanterine desired revision ve `pending/delivered/applied/failed` config senkronizasyon durumu eklendi.
- Player restart ve reboot için kalıcı SQLite komut kuyruğu eklendi.
- Cihazın komut sonucunu Hub'a bildirerek kuyruğu `completed/failed` durumuna geçirmesi eklendi.
- Ağ cevabı kaybolan `delivered` komutların tekrar teslim edilmesi sağlandı.
- Tekrar teslim edilen reboot/restart komutlarının yeniden çalıştırılmasını önlemek için cihazda son 100 komutun kalıcı sonucu saklandı.
- Cihaz ve komut sonucu endpoint'lerinde cihaz kimliği ile benzersiz token eşleşmesi yeniden doğrulandı.

### Doğrulama

- Toplam 28 otomatik test başarılı.
- Pending cihazın config almasının engellenmesi test edildi.
- Onay, desired config revision üretimi, heartbeat teslimi ve config sonucu uçtan uca doğrulandı.
- Reboot komutunun kuyruğa alınması, teslim edilmesi ve tamamlanması doğrulandı.
- Aynı komutun ağ nedeniyle yeniden tesliminde cihaz işleminin yalnızca bir kez çalıştığı doğrulandı.
- Config ve komut sonuçlarının yanlış cihaz token'ıyla değiştirilememesi sağlandı.
- Python compile ve whitespace kontrolleri başarılı.
- Merkezi config ve komut paketi `agent/hub-commands` dalına gönderildi ve draft PR `#3` açıldı; PR tabanı discovery/heartbeat dalıdır.

### Sonraki çalışma

1. Merkezi cihaz listesi web arayüzünü oluşturmak.
2. Cihaz detayında playlist editörü, Send, restart ve reboot aksiyonlarını bağlamak.
3. Sağlık durumlarını renkli liste ve uyarı eşikleriyle göstermek.
4. Hub kurulumu ve servis paketini hazırlamak.

## 2026-07-19 - Merkezi Hub web arayüzü 0.1.0

### Durum

Yerel Hub uygulaması olarak tamamlandı; canlı cihaz verisiyle görsel doğrulama bekliyor.

### Eklenenler

- FastAPI Hub içine `/ui/` altında sunulan merkezi yönetim dashboard'u eklendi.
- Admin token'ın JavaScript veya browser storage içinde tutulmaması için 12 saatlik imzalı HttpOnly oturum cookie'si eklendi.
- Oturum cookie'sinde `SameSite=Strict` kullanıldı ve HTTPS kurulumları için Secure seçeneği eklendi.
- Toplam, online, onay bekleyen ve sorunlu cihaz özet kartları eklendi.
- Tümü, online, pending ve sorunlu cihaz filtreleri eklendi.
- Cihaz listesinde aktif yayın, player, disk sağlığı ve config senkronizasyon durumu gösterildi.
- Offline, player hatası, yüksek disk kullanımı, yüksek sıcaklık, yüksek log kullanımı ve config sorunu uyarıları eklendi.
- Cihaz detay panelinde IP, CPU, RAM, boş disk, sıcaklık, log kullanımı, uptime ve revision bilgileri eklendi.
- Otomatik bulunan pending cihazı arayüzden onaylama akışı eklendi.
- Cihazın heartbeat ile bildirdiği gerçek playlist'in Hub veritabanında saklanması eklendi.
- Reported playlist'i görüntüleme, en fazla 40 satır düzenleme ve yeni revision ile `Kaydet ve gönder` akışı eklendi.
- Player restart ve kullanıcı onaylı reboot butonları komut kuyruğuna bağlandı.
- Dashboard 10 saniyede bir cihaz listesini yenileyecek şekilde ayarlandı.
- Masaüstü, tablet ve dar ekranlar için responsive görünüm eklendi.
- Sites yönergeleri gereği kalıcı cihaz verisi browser storage yerine mevcut SQLite backend'de tutuldu; yerel cihaz ağı gereksinimi nedeniyle cloud hosting yapılmadı.

### Doğrulama

- Toplam 31 otomatik test başarılı.
- Admin login, HttpOnly/SameSite cookie, logout ve yetkisiz erişim test edildi.
- Hub root yönlendirmesi ve `/ui/` statik dashboard sunumu doğrulandı.
- Cihaz heartbeat'inde reported playlist ile status revision eşleşmesi zorunlu hale getirildi.
- Reported playlist'in Hub tarafından okunması test edildi.
- JavaScript sözdizimi, Python compile ve whitespace kontrolleri başarılı.
- Kullanıcı istemediği ve canlı cihaz bulunmadığı için browser tabanlı görsel QA yapılmadı.
- Merkezi dashboard `agent/hub-ui` dalına gönderildi ve draft PR `#4` açıldı; PR tabanı merkezi config/komut dalıdır.

### Sonraki çalışma

1. Hub installer ve systemd servisini hazırlamak.
2. SQLite yedekleme ve Hub log saklama politikasını eklemek.
3. Tek makinede simüle Hub + çoklu sanal cihaz smoke testi yapmak.
4. Donanım uygun olduğunda bir Odroid ile canlı kabul testi yapmak.

## 2026-07-19 - Hub installer, yedekleme ve 15 cihaz smoke testi

### Durum

Otomatik testlerle tamamlandı; Linux systemd üzerinde canlı kurulum bekliyor.

### Eklenenler

- Debian/Ubuntu Hub makinesi için tekrar çalıştırılabilir `hub/installer/install.sh` eklendi.
- Hub uygulaması `/opt/stream-hub`, SQLite verisi `/var/lib/stream-hub` ve ayarlar `/etc/stream-hub` olarak ayrıldı.
- Hub servisi özel `stream-hub` sistem kullanıcısı ve grubu altında çalışacak şekilde hazırlandı.
- İlk kurulumda 256-bit rastgele admin token üretimi eklendi.
- Tekrar kurulumda admin token, Hub ayarları ve SQLite veritabanının korunması sağlandı.
- Hub için systemd hardening, otomatik restart ve erişim sınırları eklendi.
- Hub journal kayıtları da 7 gün, toplam 1 GB ve en az 2 GB boş alan politikasıyla sınırlandı.
- SQLite online backup API'sini kullanan günlük yedekleme betiği eklendi.
- Günlük yedekleme için systemd oneshot servis ve persistent timer eklendi.
- Yedekler en fazla 7 gün ve 7 dosya olacak şekilde sınırlandı.
- Installer sonunda Hub servis, health endpoint ve UI erişim kontrolü eklendi.

### Doğrulama

- Toplam 34 otomatik test başarılı.
- SQLite veritabanı açıkken tutarlı yedek oluşturulduğu ve yedekten kayıt okunabildiği doğrulandı.
- Fazla yedeklerin 7 dosya sınırına indirildiği doğrulandı.
- Installer'ın mevcut env/veri dizinini silmediği, parola sıfırlamadığı ve log sınırlarını içerdiği test edildi.
- 15 farklı cihazın benzersiz token ve IP ile Hub'a heartbeat göndermesi simüle edildi.
- Hub envanterinde 15 cihazın tamamının online olarak listelendiği doğrulandı.
- Toplam kaynak ağacında Python compile, JavaScript syntax, whitespace ve LF kontrolleri başarılı.

### Bekleyen canlı doğrulamalar

- Hub installer'ın gerçek Debian/Ubuntu systemd makinesinde çalıştırılması.
- Gerçek ağda mDNS multicast discovery.
- Bir Odroid üzerinde MPV/HDMI/tty1 oynatma.
- Gerçek reboot ve ağ kesintisi sonrası komut sonucu davranışı.
- Hub installer ve yedekleme paketi `agent/hub-installer` dalına gönderildi ve draft PR `#5` açıldı; PR tabanı dashboard dalıdır.

## 2026-07-19 - Yerel Hub arayüz önizlemesi

### Durum

Tamamlandı; canlı Odroid gerektirmeyen yerel demo Hub üzerinde doğrulandı.

### Yapılanlar ve doğrulama

- Hub backend yerel makinede mDNS kapalı olarak çalıştırıldı ve `/healthz` yanıtı doğrulandı.
- Arayüz 15 gerçekçi sanal Odroid kaydıyla dolduruldu: 14 online, 1 offline ve 2 onay bekleyen cihaz senaryosu oluşturuldu.
- Player servisi, yüksek disk, yüksek sıcaklık ve log kullanım sınırı sağlık uyarıları arayüzde görünür hale getirildi.
- Yönetici token oturumu ile giriş yapılarak filo özetinin, filtrelerin ve cihaz listesinin yüklendiği doğrulandı.
- Cihaz detay çekmecesinde IP, CPU/RAM, disk, sıcaklık, log kullanımı, uptime ve revision bilgilerinin gösterildiği doğrulandı.
- Oynatma listesi düzenleme, `Kaydet ve gönder`, `Player restart` ve `Cihazı reboot et` kontrollerinin görünür olduğu doğrulandı.
- Yerel yönetim paneli Codex uygulamasının tarayıcısında kullanıcıya açık bırakıldı.

## 2026-07-19 - 50 bağlantılı oynatma listesi desteği

### Durum

Tamamlandı ve otomatik testlerle doğrulandı.

### Yapılanlar

- Cihaz agent oynatma listesi sınırı 40 bağlantıdan 50 bağlantıya yükseltildi.
- Hub backend reported ve desired playlist doğrulama sınırı 50 bağlantıya yükseltildi.
- Web arayüzündeki playlist editörü 50 yayın satırı eklenmesine izin verecek şekilde güncellendi.
- Kullanıcı 50 bağlantı sınırına ulaştığında arayüzde açıklayıcı bildirim gösterilmesi eklendi.
- Ana proje dokümantasyonuna cihaz başına 50 yayın bağlantısı desteği işlendi.

### Doğrulama

- Cihaz modeliyle tam 50 bağlantılı playlist'in kabul edildiği test edildi.
- Hub modeliyle tam 50 bağlantılı playlist'in kabul edildiği test edildi.
- Hem cihaz hem Hub modellerinin 51 bağlantılı playlist'i reddettiği test edildi.
- Toplam 37 otomatik test başarıyla tamamlandı.

## 2026-07-19 - Yayın bazlı sağlık takibi

### Durum

Tamamlandı; otomatik testler ve 50 yayınlı yerel Hub arayüzüyle doğrulandı.

### Yapılanlar

- Her Odroid'in yayın URL'lerini kendi ağ bağlantısı üzerinden HLS manifest seviyesinde kontrol etmesi merkezi sağlık akışına bağlandı.
- Kontroller cihaz yükünü korumak için varsayılan 60 saniye aralık ve en fazla 6 eşzamanlı bağlantıyla sınırlandı.
- Sağlık sonuçlarının agent belleğinde önbelleğe alınması ve heartbeat ile Hub'a gönderilmesi eklendi.
- Yayın kimliği, URL, aktiflik, sağlık durumu, HTTP kodu, gecikme, hata ve son kontrol zamanı Hub SQLite veritabanında saklanmaya başlandı.
- Yönetici API'sine cihaz bazlı `GET /api/v1/devices/{device_id}/stream-health` endpoint'i eklendi.
- Web playlist editörüne her yayın için `Sağlıklı`, `Hatalı`, `Devre dışı` ve `Kontrol bekliyor` göstergeleri eklendi.
- Her satırda HTTP kodu, gecikme, hata açıklaması ve son kontrol zamanı gösterildi.
- Oynatma listesi başlığına sağlıklı ve hatalı yayın toplamları eklendi.
- Kaynak sağlığı ile aktif MPV oynatıcı durumunun ayrı sinyaller olduğu dokümante edildi.

### Doğrulama

- Heartbeat'in önbellekteki yayın sağlık sonuçlarını gönderdiği test edildi.
- Hub'ın sağlık sonuçlarını sakladığı ve yetkili API üzerinden döndürdüğü test edildi.
- Sağlık endpoint'inin yetkisiz isteği reddettiği doğrulandı.
- Toplam 38 otomatik test başarıyla tamamlandı.
- JavaScript syntax, Python compile ve whitespace kontrolleri başarılı.
- Yerel demo panelinde 50 yayın satırının 47 sağlıklı ve 3 hatalı olarak gösterildiği doğrulandı.
