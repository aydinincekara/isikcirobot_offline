"""AFİ KOD uygulamasından güncelleme paketi üretir.

Kullanım (isikcirobot_offline klasöründe, Komut İstemi; yönetici izni gerekmez):
    python tools/paketle.py ..\\isikcirobot_v1

Ne yapar?
  1. Uygulama klasöründen (index.html, js, lib ...) paketler/afi-kod-<sürüm>.zip dosyasını yapar.
     Sürüm numarası uygulamanın js/version.js dosyasından okunur.
  2. Paketin içine afi-paket.json (uygulama adı, sürüm) koyar.
  3. version.json dosyasını günceller: sunucular "Güncellemeleri denetle" deyince bu dosyaya bakar.
     Dosyada paketin SHA-256 doğrulama özeti yazar; indirilen paket bununla karşılaştırılır.
  4. Aynı paketi afi_sinif/paketler/ klasörüne de koyar: .exe yapılırken programın içine ilk paket olarak girer.
  5. En yeni 3 sürüm dışındaki eski paketleri siler (depo şişmesin).
"""
import hashlib
import json
import os
import re
import shutil
import sys
import time
import zipfile

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICERIK = ["index.html", "js", "lib", "README.md", "BENIOKU.txt", "afi-kod-kilavuz.docx"]
SAKLA = 3


def surum_oku(uyg_klasor):
    with open(os.path.join(uyg_klasor, "js", "version.js"), encoding="utf-8") as f:
        m = re.search(r"AFI_VERSION\s*=\s*'([^']+)'", f.read())
    if not m:
        raise SystemExit("js/version.js içinde sürüm bulunamadı")
    return m.group(1)


def sha256(yol):
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for p in iter(lambda: f.read(1 << 16), b""):
            h.update(p)
    return h.hexdigest()


def paketle(uyg_klasor, notlar_tr="", notlar_en=""):
    uyg_klasor = os.path.abspath(uyg_klasor)
    surum = surum_oku(uyg_klasor)
    hedef_klasor = os.path.join(KOK, "paketler")
    os.makedirs(hedef_klasor, exist_ok=True)
    zip_ad = "afi-kod-%s.zip" % surum
    zip_yol = os.path.join(hedef_klasor, zip_ad)
    manifest = {"uygulama": "afi-kod", "ad": "AFİ KOD", "surum": surum, "giris": "index.html", "olusturma": time.strftime("%Y-%m-%d %H:%M")}
    with zipfile.ZipFile(zip_yol, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("afi-paket.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for ad in ICERIK:
            tam = os.path.join(uyg_klasor, ad)
            if os.path.isfile(tam):
                z.write(tam, ad)
            elif os.path.isdir(tam):
                for kok, _, dosyalar in os.walk(tam):
                    for d in sorted(dosyalar):
                        p = os.path.join(kok, d)
                        z.write(p, os.path.relpath(p, uyg_klasor).replace(os.sep, "/"))
    ozet = sha256(zip_yol)
    vj_yol = os.path.join(KOK, "version.json")
    try:
        with open(vj_yol, encoding="utf-8") as f:
            vj = json.load(f)
    except (OSError, ValueError):
        vj = {}
    vj.setdefault("platform", {})
    try:
        sys.path.insert(0, KOK)
        from afi_sinif import ortak
        vj["platform"]["surum"] = ortak.PLATFORM_SURUM
    except ImportError:
        pass
    vj.setdefault("uygulamalar", {})
    eski = vj["uygulamalar"].get("afi-kod", {})
    vj["uygulamalar"]["afi-kod"] = {"ad": "AFİ KOD", "surum": surum, "zip": "paketler/" + zip_ad, "sha256": ozet, "boyut": os.path.getsize(zip_yol),
                                    "tarih": time.strftime("%Y-%m-%d"),
                                    "notlar": {"tr": notlar_tr or eski.get("notlar", {}).get("tr", ""), "en": notlar_en or eski.get("notlar", {}).get("en", "")}}
    with open(vj_yol, "w", encoding="utf-8") as f:
        json.dump(vj, f, ensure_ascii=False, indent=1)
    gomulu = os.path.join(KOK, "afi_sinif", "paketler")
    if os.path.isdir(gomulu):
        shutil.rmtree(gomulu)
    os.makedirs(gomulu)
    shutil.copyfile(zip_yol, os.path.join(gomulu, zip_ad))
    hepsi = sorted([f for f in os.listdir(hedef_klasor) if f.startswith("afi-kod-") and f.endswith(".zip")],
                   key=lambda f: tuple(int(x) if x.isdigit() else 0 for x in f[8:-4].split(".")))
    for f in hepsi[:-SAKLA]:
        os.remove(os.path.join(hedef_klasor, f))
    print("Paket: %s (%d KB)\nSHA-256: %s\nversion.json güncellendi." % (zip_yol, os.path.getsize(zip_yol) // 1024, ozet))
    return zip_yol, ozet, surum


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    paketle(sys.argv[1], *(sys.argv[2:4]))
