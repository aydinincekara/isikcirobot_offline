# afi sınıf — AFİ KOD sınıf sürümü

Öğretmen bilgisayarında çalışan **sınıf sunucusu** ve öğrenci bilgisayarlarına kurulan **istemci**.
İndirme ve kurulum sayfası: https://aydinincekara.github.io/isikcirobot_offline/

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
- `tests/` — testler: `python -m unittest discover tests`
- `.github/workflows/exe.yml` — exe dosyalarını GitHub'da üretir

## Yeni AFİ KOD sürümünü yayınlamak
1. isikcirobot_v1'de `python tools/set_version.py 2.4`, değişiklikleri gönderin.
2. Bu klasörde: `python tools/paketle.py ..\isikcirobot_v1 "Türkçe not" "English note"`
3. `paketler/`, `version.json` ve `afi_sinif/paketler/` değişikliklerini gönderin. Sunucular "Güncellemeleri denetle" deyince yeni sürümü görür.

## exe üretmek
GitHub → Actions → **Windows programlari** → Run workflow (dosyalar "Artifacts" altında çıkar) ya da etiket gönderin:
`git tag v1.0.1` ve `git push --tags` → Releases sayfasına konur, indirme sayfasındaki düğmeler en yeni sürümü verir.

## Başka dersler
Her ders bir uygulama paketidir: zip içinde `afi-paket.json` (`{"uygulama": "...", "ad": "...", "surum": "...", "giris": "index.html"}`) ve uygulama dosyaları. Uygulama, sınıf modunu `/api/v1/` uçlarıyla kullanır (AFİ KOD'daki `js/sinif.js` örnektir).
