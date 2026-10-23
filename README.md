# afi sınıf — AFİ KOD sınıf sürümü

Öğretmen bilgisayarında çalışan **sınıf sunucusu** ve öğrenci bilgisayarlarına kurulan **istemci**.
İndirme ve kurulum sayfası: https://aydinincekara.github.io/isikcirobot_offline/

Tek kurulum dosyası **`afi-sinif-kurulum.exe`**: sihirbazda lisans onayı, kurulum türü (öğretmen/öğrenci), role göre ayarlar ve klasör seçilir; yeniden açılınca güncelleme, tür değiştirme ve kaldırma sunar. İçinde iki program vardır:

| Program | Nerede | Ne yapar |
|---|---|---|
| `afi-sunucu.exe` | Öğretmen bilgisayarı | AFİ KOD'u sınıfa sunar; öğretmen paneli (admin/öğretmen girişi, ağ aralığına göre canlı takip, şu anki bloklar, mesaj, CSV), GitHub'dan güncelleme ve geri alma |
| `afi-istemci.exe` | Öğrenci bilgisayarı | AFİ KOD'u bu bilgisayardan açar (`127.0.0.1:8100`); ağ yokken de çalışır, kayıtları bekletir; sunucuyu kendisi bulur; güncellemeleri sunucudan alır |

## Klasörler
- `afi_sinif/ortak.py` — ortak parçalar: paket deposu (SHA-256 doğrulama, güvenli açma, sürüm seçme), HTTP temel sınıfı, ağ aralıkları
- `afi_sinif/sunucu.py` — sınıf sunucusu (SQLite), API `/api/v1/...`
- `afi_sinif/istemci.py` — öğrenci istemcisi
- `afi_sinif/panel/` — öğretmen paneli (HTML/CSS/JS)
- `afi_sinif/paketler/` — exe'nin içine giren ilk uygulama paketi
- `paketler/`, `version.json` — sunucuların "Güncellemeleri denetle" ile baktığı yayın
- `tools/paketle.py` — AFİ KOD klasöründen yeni paket üretir
- `kurulum/` — kurulum sihirbazı: `afi-sinif.iss` (Inno Setup), `LISANS.txt`, görseller (`gorseller.py` ile çizilir), denetim betikleri
- `tests/` — testler: `python -m unittest discover tests`
- `.github/workflows/exe.yml` — exe dosyalarını GitHub'da üretir

## Sessiz kurulum
Yönetici Komut İstemi'nde: `afi-sinif-kurulum.exe /VERYSILENT /ALLUSERS /ROL=istemci [/SUNUCU=192.168.1.20:8000]`
ya da `/ROL=sunucu /PORT=8000 /AD="Bilgi Evi 1" [/VERI=klasör]`. Diğerleri: `/BASLANGIC=0|1 /MASAUSTU=0|1 /DUVAR=0|1 /ORTAK=0|1 /DIR=klasör`.

## Yeni AFİ KOD sürümünü yayınlamak
1. isikcirobot_v1'de `python tools/set_version.py 2.4`, değişiklikleri gönderin.
2. Bu klasörde: `python tools/paketle.py ..\isikcirobot_v1 "Türkçe not" "English note"`
3. `paketler/`, `version.json` ve `afi_sinif/paketler/` değişikliklerini gönderin. Sunucular "Güncellemeleri denetle" deyince yeni sürümü görür.

## exe üretmek
Program kodu (`afi_sinif/`, `kurulum/`) main dalına gönderilince GitHub exe'leri ve kurulum dosyasını kendisi üretir; sessiz kurulum, rol değiştirme ve kaldırmayı gerçek Windows'ta dener, sihirbazın ekran görüntülerini `ekranlar` dalına koyar ve kurulum dosyasını Releases sayfasına yükler (sürüm adı `afi_sinif/ortak.py` içindeki `PLATFORM_SURUM`; yeni sürüm için bu sayıyı artırın). Elle başlatmak: GitHub → Actions → **Windows programlari** → Run workflow. İndirme sayfasındaki düğmeler hep en yeni sürümü verir.

## Başka dersler
Her ders bir uygulama paketidir: zip içinde `afi-paket.json` (`{"uygulama": "...", "ad": "...", "surum": "...", "giris": "index.html"}`) ve uygulama dosyaları. Uygulama, sınıf modunu `/api/v1/` uçlarıyla kullanır (AFİ KOD'daki `js/sinif.js` örnektir).
