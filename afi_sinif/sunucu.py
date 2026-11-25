"""afi sınıf sunucusu - öğretmen bilgisayarında çalışır.

- AFİ KOD'u (ve ileride başka ders uygulamalarını) yerel ağa sunar: öğrenciler http://ogretmen-pc:8000 adresini açar.
- Öğrencilerin ilerlemesini ve canlı durumunu toplar; öğretmen panelinde gösterir (/panel).
- Admin ve öğretmen hesapları; her öğretmen yalnızca kendi ağ aralığındaki öğrencileri görür.
- Öğrenci istemcilerine (afi-istemci) güncel uygulama paketini dağıtır.
- GitHub'daki isikcirobot_offline sayfasından yeni sürümü denetler, indirir, doğrular ve kurar; önceki sürüme dönülebilir.
"""
import argparse
import contextlib
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from http.server import ThreadingHTTPServer

from . import ortak
from .ortak import Hata, simdi

CEVRIMICI_SN = 75       # son nabızdan bu kadar saniye geçmediyse öğrenci "bağlı" sayılır (arka plandaki sekmeler dakikada bir nabız atar)
SURE_ARALIK = 90        # iki nabız arası bundan uzunsa o aralık çalışma süresine eklenmez
BOS_SN = 180            # öğrenci bu kadar saniyedir fareye/klavyeye dokunmadıysa süre sayılmaz
OTURUM_SN = 12 * 3600
YEDEK_SAKLA = 14        # günlük otomatik yedeklerden kaç tanesi saklanır
KOMUTLAR = {            # öğretmenin öğrenci bilgisayarlarına gönderebildiği komutlar
    "duzen-sifirla": "Ekran düzeni varsayılana döndürüldü",
    "misafir-temizle": "Misafir çalışmaları temizlendi",
    "liste-temizle": "Bilgisayardaki öğrenci listesi temizlendi",
}
_AD_ONBELLEK = {}


def ip_adi(ip):
    """IP adresinden bilgisayar adını bulur (arka planda, önbellekli). Bulunamazsa boş döner."""
    if ip in _AD_ONBELLEK:
        return _AD_ONBELLEK[ip]
    _AD_ONBELLEK[ip] = ""

    def bul():
        try:
            ad = socket.gethostbyaddr(ip)[0].split(".")[0]
            _AD_ONBELLEK[ip] = "" if ad.replace("-", "").replace(".", "").isdigit() else ad.upper()
        except (OSError, UnicodeError):
            pass
    threading.Thread(target=bul, daemon=True).start()
    return ""


# ======================================================================= veritabanı
SEMA = """
CREATE TABLE IF NOT EXISTS kullanici (id INTEGER PRIMARY KEY, kullanici TEXT UNIQUE, ad TEXT, rol TEXT, tuz TEXT, ozet TEXT, araliklar TEXT, olusturma REAL);
CREATE TABLE IF NOT EXISTS oturum (belirtec TEXT PRIMARY KEY, kullanici_id INTEGER, bitis REAL);
CREATE TABLE IF NOT EXISTS ogrenci (anahtar TEXT, uygulama TEXT, ad TEXT, robot TEXT, ip TEXT, cihaz TEXT, istemci INTEGER,
  ilk REAL, son REAL, adim TEXT, adim_ad TEXT, durum TEXT, yildiz INTEGER, biten INTEGER, son_mesaj INTEGER DEFAULT 0, PRIMARY KEY (anahtar, uygulama));
CREATE TABLE IF NOT EXISTS ilerleme (anahtar TEXT, uygulama TEXT, veri TEXT, guncelleme REAL, PRIMARY KEY (anahtar, uygulama));
CREATE TABLE IF NOT EXISTS anlik (anahtar TEXT, uygulama TEXT, adim TEXT, ws TEXT, kod TEXT, guncelleme REAL, PRIMARY KEY (anahtar, uygulama));
CREATE TABLE IF NOT EXISTS mesaj (id INTEGER PRIMARY KEY AUTOINCREMENT, hedef TEXT, araliklar TEXT, metin TEXT, tur TEXT, gonderen TEXT, zaman REAL);
CREATE TABLE IF NOT EXISTS olay (id INTEGER PRIMARY KEY AUTOINCREMENT, zaman REAL, anahtar TEXT, uygulama TEXT, tur TEXT, adim TEXT, ayrinti TEXT);
CREATE INDEX IF NOT EXISTS olay_ogr ON olay (anahtar, uygulama);
CREATE TABLE IF NOT EXISTS ayar (ad TEXT PRIMARY KEY, deger TEXT);
CREATE TABLE IF NOT EXISTS kayit (id INTEGER PRIMARY KEY AUTOINCREMENT, no TEXT UNIQUE, ad TEXT, sinif TEXT, robot TEXT, notu TEXT, olusturma REAL, guncelleme REAL);
CREATE TABLE IF NOT EXISTS esleme (anahtar TEXT, pid TEXT, kayit_id INTEGER, PRIMARY KEY (anahtar, pid));
CREATE TABLE IF NOT EXISTS gunluk (anahtar TEXT, uygulama TEXT, gun TEXT, sure REAL DEFAULT 0, basari INTEGER DEFAULT 0, hata INTEGER DEFAULT 0, ilk REAL, son REAL, PRIMARY KEY (anahtar, uygulama, gun));
CREATE TABLE IF NOT EXISTS ses_ayar (anahtar TEXT PRIMARY KEY, deger TEXT);
"""

# 1.2 ve 1.3 ile eklenen sütunlar: eski veritabanı açılınca kendiliğinden eklenir
OGRENCI_EK = [("oturum", "TEXT"), ("pid", "TEXT"), ("adim_bas", "REAL"), ("adim_hata", "INTEGER DEFAULT 0"), ("adim_yildiz", "INTEGER DEFAULT 0"),
              ("bos", "REAL DEFAULT 0"), ("sure", "REAL DEFAULT 0"), ("yardim", "REAL"), ("cakisma", "REAL"), ("sifir", "REAL DEFAULT 0")]


class Veritabani:
    def __init__(self, yol):
        self.yol = yol
        self.kilit = threading.RLock()
        self.b = sqlite3.connect(yol, check_same_thread=False)
        self.b.row_factory = sqlite3.Row
        self._derinlik = 0
        with self.kilit:
            self.b.executescript(SEMA)
            sutunlar = [r[1] for r in self.b.execute("PRAGMA table_info(ogrenci)")]
            for ad, tur in OGRENCI_EK:
                if ad not in sutunlar:
                    self.b.execute("ALTER TABLE ogrenci ADD COLUMN %s %s" % (ad, tur))
            self.b.execute("PRAGMA journal_mode=WAL")
            self.b.execute("PRAGMA synchronous=NORMAL")     # WAL ile güvenli; eski disklerde her kayıtta bekletmez
            self.b.commit()

    def sorgu(self, sql, parametre=()):
        with self.kilit:
            return [dict(r) for r in self.b.execute(sql, parametre).fetchall()]

    def tek(self, sql, parametre=()):
        r = self.sorgu(sql, parametre)
        return r[0] if r else None

    def yap(self, sql, parametre=()):
        with self.kilit:
            c = self.b.execute(sql, parametre)
            if not self._derinlik:
                self.b.commit()
            return c.lastrowid

    @contextlib.contextmanager
    def toplu(self):
        """Birbirine bağlı birkaç yazmayı tek seferde kaydeder: ya hepsi olur ya hiçbiri (yarım kalmış kayıt oluşmaz)."""
        with self.kilit:
            self._derinlik += 1
            try:
                yield
            except BaseException:
                if self._derinlik == 1:
                    self.b.rollback()
                raise
            else:
                if self._derinlik == 1:
                    self.b.commit()
            finally:
                self._derinlik -= 1

    def ayar(self, ad, varsayilan=None):
        r = self.tek("SELECT deger FROM ayar WHERE ad=?", (ad,))
        return json.loads(r["deger"]) if r else varsayilan

    def ayar_yaz(self, ad, deger):
        self.yap("INSERT OR REPLACE INTO ayar (ad, deger) VALUES (?, ?)", (ad, json.dumps(deger, ensure_ascii=False)))

    def yedekle(self, hedef):
        with self.kilit:
            yeni = sqlite3.connect(hedef)
            self.b.backup(yeni)
            yeni.close()


# ======================================================================= parolalar
def parola_ozet(parola, tuz=None):
    """PBKDF2-HMAC-SHA256: parola düz metin olarak hiçbir yerde saklanmaz."""
    tuz = tuz or secrets.token_hex(16)
    ozet = hashlib.pbkdf2_hmac("sha256", parola.encode("utf-8"), bytes.fromhex(tuz), 200000)
    return tuz, ozet.hex()


def parola_dogru(parola, tuz, ozet):
    return hmac.compare_digest(parola_ozet(parola, tuz)[1], ozet)


# ======================================================================= ilerleme birleştirme
def ilerleme_birlestir(eski, yeni):
    """Yıldızlarda büyük olan kalır; bloklarda yeni gelen kazanır; görülen hikâyeler birleşir.
    "sifir": öğretmenin (ya da öğrencinin) ilerlemeyi sıfırladığı an. Sıfırlamadan önceye ait veri, sonrakiyle birleştirilmez
    (yoksa öğrencinin bilgisayarında kalan eski yıldızlar sıfırlanan kaydı geri doldururdu).
    "sifirla": öğrenci "Baştan başla"ya bastı ama sunucu bunu henüz onaylamadı. Onaylanana kadar eski veri bu kayda karışmaz;
    sunucu isteği alınca kendi saatiyle "sifir" yazar ve bayrağı kaldırır."""
    eski = dict(eski or {})
    yeni = yeni or {}
    try:
        es, ys = float(eski.get("sifir") or 0), float(yeni.get("sifir") or 0)
    except (TypeError, ValueError):
        es = ys = 0
    istek = yeni.get("sifirla")
    if istek and istek not in (eski.get("sifirla"), eski.get("sifirla_son")):
        eski = {"sifirla": istek, "sifir": max(es, ys)}       # yeni bir sıfırlama isteği: eldeki her şey atılır, yalnızca istekten sonraki çalışma kalır
    elif eski.get("sifirla") and not istek and ys <= es:      # sıfırlama onay bekliyor; gelen veri sıfırlamadan önceye ait
        return eski
    elif istek and istek == eski.get("sifirla_son"):
        pass                                                   # işlenmiş isteğin tekrarı: gelen veri sıfırlamadan sonraki çalışmadır, birleşir
    elif es > ys:
        return eski
    elif ys > es:
        eski = {"sifir": ys}
    yildiz = dict(eski.get("stars") or {})
    for k, v in (yeni.get("stars") or {}).items():
        try:
            yildiz[k] = max(int(yildiz.get(k) or 0), int(v or 0))
        except (TypeError, ValueError):
            continue
    ws = dict(eski.get("ws") or {})
    ws.update(yeni.get("ws") or {})
    gorulen = dict(eski.get("seen") or {})
    gorulen.update(yeni.get("seen") or {})
    eski.update({"stars": yildiz, "ws": ws, "seen": gorulen})
    # Kalınan adım: gezinme sayacı (lastN) büyük ya da eşit olan tarafınki geçerlidir.
    # Böylece uzun süredir açılmamış bir bilgisayardaki eski kayıt, öğrencinin yeni kaldığı yeri ezmez.
    if yeni.get("last"):
        try:
            yn, en = int(yeni.get("lastN") or 0), int(eski.get("lastN") or 0)
        except (TypeError, ValueError):
            yn = en = 0
        if yn >= en or not eski.get("last"):
            eski["last"] = yeni["last"]
            eski["lastN"] = max(yn, en)
    return eski


# ======================================================================= sunucu
class Sunucu:
    def __init__(self, veri_klasoru, port=ortak.VARSAYILAN_PORT, ad=None, guncelleme_adresi=None, sessiz=False):
        self.veri = veri_klasoru
        os.makedirs(veri_klasoru, exist_ok=True)
        self.port = port
        self.sessiz = sessiz
        self.db = Veritabani(os.path.join(veri_klasoru, "afi-sinif.db"))
        self.paketler = ortak.PaketDeposu(os.path.join(veri_klasoru, "paketler"))
        self.gunluk_dosya = os.path.join(veri_klasoru, "gunluk.txt")
        self.ad = ad or self.db.ayar("sunucu_adi") or ("afi sınıf - " + ortak.bilgisayar_adi())
        if guncelleme_adresi:
            self.db.ayar_yaz("guncelleme_adresi", guncelleme_adresi)
        self.son_denetim = None
        self.baslangic = simdi()
        self.kapat = None              # calistir() doldurur: sunucuyu kapatan işlev
        self.guncelleme_durum = {"calisiyor": False, "mesaj": ""}
        self.kilit = threading.Lock()
        self.cihazlar = {}             # bağlı öğrenci bilgisayarları: {cihaz kimliği: {ip, ad, son, anahtar}} (yalnızca bellekte)
        kurulan = self.paketler.gomulu_paketleri_kur()
        for k in kurulan:
            self.gunluk("Program içindeki paket kuruldu: " + k)

    # ------------------------------------------------------------ yardımcılar
    def gunluk(self, satir):
        try:
            with open(self.gunluk_dosya, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + satir + "\n")
            if os.path.getsize(self.gunluk_dosya) > 5 * 1024 * 1024:
                os.replace(self.gunluk_dosya, self.gunluk_dosya + ".eski")
        except OSError:
            pass

    def guncelleme_adresi(self):
        return self.db.ayar("guncelleme_adresi") or ortak.GUNCELLEME_ADRESI

    def kullanici_sayisi(self):
        return self.db.tek("SELECT COUNT(*) AS n FROM kullanici")["n"]

    def kullanici_ekle(self, kullanici, ad, parola, rol="ogretmen", araliklar=None):
        kullanici = (kullanici or "").strip().lower()
        if not kullanici or len(kullanici) > 40 or not kullanici.replace(".", "").replace("_", "").replace("-", "").isalnum():
            raise Hata(400, "Kullanıcı adı sadece harf, rakam, nokta, alt çizgi ve tire içerebilir.")
        if not parola or len(parola) < 6:
            raise Hata(400, "Parola en az 6 karakter olmalı.")
        if rol not in ("admin", "ogretmen"):
            raise Hata(400, "Rol admin ya da ogretmen olmalı.")
        araliklar = [a.strip() for a in (araliklar or []) if a and a.strip()]
        for a in araliklar:
            if not ortak.aralik_gecerli(a):
                raise Hata(400, "Ağ aralığı anlaşılmadı: " + a + " (örnek: 192.168.1.0/24 ya da 192.168.1.10-192.168.1.40)")
        if self.db.tek("SELECT id FROM kullanici WHERE kullanici=?", (kullanici,)):
            raise Hata(409, "Bu kullanıcı adı zaten var.")
        tuz, ozet = parola_ozet(parola)
        return self.db.yap("INSERT INTO kullanici (kullanici, ad, rol, tuz, ozet, araliklar, olusturma) VALUES (?,?,?,?,?,?,?)",
                           (kullanici, (ad or kullanici)[:60], rol, tuz, ozet, json.dumps(araliklar), simdi()))

    def gorebilir(self, kullanici, ip):
        if kullanici["rol"] == "admin":
            return True
        araliklar = json.loads(kullanici.get("araliklar") or "[]")
        if not araliklar:
            return True       # aralık verilmemiş öğretmen her şeyi görür (tek sınıflı kurumlar için)
        return ortak.aralikta(ip, araliklar)

    # ------------------------------------------------------------ öğrenci kimliği (sınıf listesi ve numaralar)
    def giris_kipi(self):
        """serbest: öğrenci adını yazarak ya da numarasıyla girer.  numara: yalnızca öğretmenin verdiği numarayla girilir."""
        return self.db.ayar("giris_kipi") or "serbest"

    def kayit_bul(self, kid=None, no=None):
        if kid:
            return self.db.tek("SELECT * FROM kayit WHERE id=?", (int(kid),))
        if no:
            return self.db.tek("SELECT * FROM kayit WHERE no=?", (str(no),))
        return None

    @staticmethod
    def kimlik_bilgi(k):
        return {"kayit": k["id"], "no": k["no"], "ad": k["ad"], "robot": k["robot"] or "afi", "sinif": k["sinif"] or ""} if k else None

    def kimlik_coz(self, ogr):
        """Uygulamadan gelen öğrenci bilgisinden (ad, robot, pid, kayit) kayıt anahtarını bulur.
        Döner: (anahtar, sınıf listesindeki kayıt ya da None).
        - Numarayla giren öğrenci "kayit" gönderir -> anahtar "#<kayıt>"; hangi bilgisayara oturursa otursun aynı kişidir.
        - Adını kendisi yazmış öğrenciye öğretmen sonradan numara verdiyse, o tarayıcıdaki profil (pid) eşlemeden tanınır."""
        ogr = ogr or {}
        k = None
        kid = ortak.kayit_no(ogr)
        if kid:
            k = self.kayit_bul(kid=kid)
        ham = ortak.anahtar_yap(ogr.get("ad"), ogr.get("robot"))
        if not k and not ham.startswith("|"):
            pid = str(ogr.get("pid") or "")[:40]
            e = self.db.tek("SELECT kayit_id FROM esleme WHERE anahtar=? AND pid IN (?, '') ORDER BY pid DESC LIMIT 1", (ham, pid))
            if e:
                k = self.kayit_bul(kid=e["kayit_id"])
        if k:
            return "#%d" % k["id"], k
        return ham, None

    def ogrenci_giris(self, v):
        """Öğrenci numarasıyla (ya da daha önce alınmış kayıt numarasıyla) giriş: adı, robotu ve sınıfı döner."""
        k = None
        if v.get("no") not in (None, ""):
            no = ortak.no_duzelt(v.get("no"))
            k = self.kayit_bul(no=no) if no else None
        elif ortak.kayit_no(v):
            k = self.kayit_bul(kid=ortak.kayit_no(v))
        if not k:
            time.sleep(0.3)      # numara denemelerini yavaşlatır
            raise Hata(404, "Bu numara sınıf listesinde yok. Numaranı kontrol et ya da öğretmenine sor.")
        return {"ok": True, "kimlik": self.kimlik_bilgi(k)}

    def yeni_no(self):
        """Kullanılmayan rastgele 4 haneli numara (dolmuşsa 5 haneli). Sıralı değil: komşusunun numarasını tahmin etmesin."""
        for hane in (4, 5, 6):
            taban = 10 ** (hane - 1)
            for _ in range(300):
                no = str(taban + secrets.randbelow(9 * taban))
                if not self.kayit_bul(no=no):
                    return no
        raise Hata(500, "Boş numara bulunamadı.")

    def kayit_ekle(self, ad, sinif="", no=None, robot=None, notu=""):
        ad = " ".join(str(ad or "").split())[:40]
        if not ad:
            raise Hata(400, "Öğrenci adı boş olamaz.")
        with self.db.toplu():
            if no in (None, ""):
                no = self.yeni_no()
            else:
                ham = no
                no = ortak.no_duzelt(no)
                if not no:
                    raise Hata(400, "Numara 2-8 haneli bir sayı olmalı: " + str(ham))
                eski = self.kayit_bul(no=no)
                if eski:
                    raise Hata(409, "%s numarası zaten %s adlı öğrencide." % (no, eski["ad"]))
            kid = self.db.yap("INSERT INTO kayit (no, ad, sinif, robot, notu, olusturma, guncelleme) VALUES (?,?,?,?,?,?,?)",
                              (no, ad, " ".join(str(sinif or "").split())[:40], str(robot or "afi")[:20], str(notu or "")[:300], simdi(), simdi()))
        return self.kayit_bul(kid=kid)

    def kayit_guncelle(self, kid, v):
        k = self.kayit_bul(kid=kid)
        if not k:
            raise Hata(404, "Öğrenci bulunamadı.")
        ad = " ".join(str(v.get("ad", k["ad"]) or "").split())[:40]
        if not ad:
            raise Hata(400, "Öğrenci adı boş olamaz.")
        no = k["no"]
        if "no" in v and str(v["no"] or "").strip() != k["no"]:
            no = ortak.no_duzelt(v["no"])
            if not no:
                raise Hata(400, "Numara 2-8 haneli bir sayı olmalı.")
            eski = self.kayit_bul(no=no)
            if eski and eski["id"] != k["id"]:
                raise Hata(409, "%s numarası zaten %s adlı öğrencide." % (no, eski["ad"]))
        sinif = " ".join(str(v.get("sinif", k["sinif"]) or "").split())[:40]
        with self.db.toplu():
            self.db.yap("UPDATE kayit SET ad=?, sinif=?, no=?, notu=?, guncelleme=? WHERE id=?", (ad, sinif, no, str(v.get("notu", k["notu"]) or "")[:300], simdi(), k["id"]))
            self.db.yap("UPDATE ogrenci SET ad=? WHERE anahtar=?", (ad, "#%d" % k["id"]))
        return self.kayit_bul(kid=kid)

    def toplu_ekle(self, metin, sinif=""):
        """Her satırda bir öğrenci. Satır "Ad Soyad" ya da "numara;Ad Soyad" / "Ad Soyad;numara" olabilir (Excel'den yapıştırma)."""
        eklenen, hatalar = [], []
        for satir in str(metin or "").replace("\r", "").split("\n"):
            parcalar = [p.strip() for p in satir.replace("\t", ";").replace(",", ";").split(";") if p.strip()]
            if not parcalar:
                continue
            no = None
            sayilar = [p for p in parcalar if p.isdigit()]
            if sayilar:
                no = sayilar[0]
                parcalar = [p for p in parcalar if p is not sayilar[0]]
            ad = " ".join(parcalar)
            try:
                eklenen.append(self.kimlik_bilgi(self.kayit_ekle(ad, sinif, no=no)))
            except Hata as h:
                hatalar.append({"satir": satir.strip(), "hata": h.mesaj})
            if len(eklenen) >= 400:
                break
        if eklenen:
            self.gunluk("Sınıf listesine %d öğrenci eklendi (%s)" % (len(eklenen), sinif or "sınıfsız"))
        return {"ok": True, "eklenen": eklenen, "hatalar": hatalar}

    def _veri_sil(self, anahtar):
        for t in ("ogrenci", "ilerleme", "anlik", "olay", "gunluk", "ses_ayar"):
            self.db.yap("DELETE FROM " + t + " WHERE anahtar=?", (anahtar,))
        self.db.yap("DELETE FROM mesaj WHERE hedef=?", (anahtar,))

    def kayit_sil(self, kid):
        k = self.kayit_bul(kid=kid)
        if not k:
            raise Hata(404, "Öğrenci bulunamadı.")
        with self.db.toplu():
            self._veri_sil("#%d" % k["id"])
            self.db.yap("DELETE FROM esleme WHERE kayit_id=?", (k["id"],))
            self.db.yap("DELETE FROM kayit WHERE id=?", (k["id"],))
        self.gunluk("Öğrenci silindi: %s (no %s)" % (k["ad"], k["no"]))
        return {"ok": True}

    def numarasiz_sil(self, anahtar):
        if anahtar.startswith("#") or not self.db.tek("SELECT 1 AS v FROM ogrenci WHERE anahtar=?", (anahtar,)):
            raise Hata(404, "Öğrenci bulunamadı.")
        with self.db.toplu():
            self._veri_sil(anahtar)
            self.db.yap("DELETE FROM esleme WHERE anahtar=?", (anahtar,))
        return {"ok": True}

    @staticmethod
    def _ozet(veri):
        """Kayıtlı ilerlemeden (toplam yıldız, biten adım sayısı)."""
        y = []
        for x in ((veri or {}).get("stars") or {}).values():
            try:
                y.append(int(x or 0))
            except (TypeError, ValueError):
                pass
        return sum(y), len([x for x in y if x])

    def _ozet_guncelle(self, anahtar):
        """Öğrenci satırındaki toplam yıldız ve biten adım sayısını kayıtlı ilerlemeden yeniden hesaplar."""
        for r in self.db.sorgu("SELECT uygulama, veri FROM ilerleme WHERE anahtar=?", (anahtar,)):
            self.db.yap("UPDATE ogrenci SET yildiz=?, biten=? WHERE anahtar=? AND uygulama=?", self._ozet(json.loads(r["veri"])) + (anahtar, r["uygulama"]))

    def _tasi(self, eski, yeni):
        """eski anahtardaki bütün kayıtları yeni anahtara taşır; yenide de kayıt varsa ikisini birleştirir (hiçbir yıldız kaybolmaz)."""
        if eski == yeni:
            return
        db = self.db
        with db.toplu():
            for r in db.sorgu("SELECT uygulama, veri FROM ilerleme WHERE anahtar=?", (eski,)):
                iy = db.tek("SELECT veri FROM ilerleme WHERE anahtar=? AND uygulama=?", (yeni, r["uygulama"]))
                birlesik = ilerleme_birlestir(json.loads(iy["veri"]) if iy else {}, json.loads(r["veri"]))
                db.yap("INSERT OR REPLACE INTO ilerleme (anahtar, uygulama, veri, guncelleme) VALUES (?,?,?,?)", (yeni, r["uygulama"], json.dumps(birlesik, ensure_ascii=False), simdi()))
            db.yap("DELETE FROM ilerleme WHERE anahtar=?", (eski,))
            for r in db.sorgu("SELECT * FROM ogrenci WHERE anahtar=?", (eski,)):
                y = db.tek("SELECT * FROM ogrenci WHERE anahtar=? AND uygulama=?", (yeni, r["uygulama"]))
                if not y:
                    db.yap("UPDATE ogrenci SET anahtar=? WHERE anahtar=? AND uygulama=?", (yeni, eski, r["uygulama"]))
                    continue
                if (r["son"] or 0) > (y["son"] or 0):      # en son görülen bilgisayarın canlı durumu kalır
                    alanlar = ("ip", "cihaz", "istemci", "oturum", "son", "adim", "adim_ad", "durum", "adim_bas", "adim_hata", "adim_yildiz", "bos", "pid")
                    db.yap("UPDATE ogrenci SET " + ", ".join(a + "=?" for a in alanlar) + " WHERE anahtar=? AND uygulama=?",
                           tuple(r[a] for a in alanlar) + (yeni, r["uygulama"]))
                db.yap("UPDATE ogrenci SET ilk=?, sure=?, son_mesaj=? WHERE anahtar=? AND uygulama=?",
                       (min(x for x in (r["ilk"], y["ilk"]) if x) if (r["ilk"] or y["ilk"]) else None, (r["sure"] or 0) + (y["sure"] or 0),
                        max(r["son_mesaj"] or 0, y["son_mesaj"] or 0), yeni, r["uygulama"]))
                db.yap("DELETE FROM ogrenci WHERE anahtar=? AND uygulama=?", (eski, r["uygulama"]))
            for r in db.sorgu("SELECT uygulama, guncelleme FROM anlik WHERE anahtar=?", (eski,)):
                y = db.tek("SELECT guncelleme FROM anlik WHERE anahtar=? AND uygulama=?", (yeni, r["uygulama"]))
                if y and (y["guncelleme"] or 0) >= (r["guncelleme"] or 0):
                    db.yap("DELETE FROM anlik WHERE anahtar=? AND uygulama=?", (eski, r["uygulama"]))
                else:
                    db.yap("DELETE FROM anlik WHERE anahtar=? AND uygulama=?", (yeni, r["uygulama"]))
                    db.yap("UPDATE anlik SET anahtar=? WHERE anahtar=? AND uygulama=?", (yeni, eski, r["uygulama"]))
            db.yap("UPDATE olay SET anahtar=? WHERE anahtar=?", (yeni, eski))
            for r in db.sorgu("SELECT * FROM gunluk WHERE anahtar=?", (eski,)):
                y = db.tek("SELECT * FROM gunluk WHERE anahtar=? AND uygulama=? AND gun=?", (yeni, r["uygulama"], r["gun"]))
                if not y:
                    db.yap("UPDATE gunluk SET anahtar=? WHERE anahtar=? AND uygulama=? AND gun=?", (yeni, eski, r["uygulama"], r["gun"]))
                    continue
                ilkler, sonlar = [x for x in (r["ilk"], y["ilk"]) if x], [x for x in (r["son"], y["son"]) if x]
                db.yap("UPDATE gunluk SET sure=?, basari=?, hata=?, ilk=?, son=? WHERE anahtar=? AND uygulama=? AND gun=?",
                       ((r["sure"] or 0) + (y["sure"] or 0), (r["basari"] or 0) + (y["basari"] or 0), (r["hata"] or 0) + (y["hata"] or 0),
                        min(ilkler) if ilkler else None, max(sonlar) if sonlar else None, yeni, r["uygulama"], r["gun"]))
            db.yap("DELETE FROM gunluk WHERE anahtar=?", (eski,))
            db.yap("UPDATE mesaj SET hedef=? WHERE hedef=?", (yeni, eski))
            db.yap("UPDATE OR IGNORE ses_ayar SET anahtar=? WHERE anahtar=?", (yeni, eski))
            db.yap("DELETE FROM ses_ayar WHERE anahtar=?", (eski,))
            self._ozet_guncelle(yeni)

    def numara_ver(self, anahtar, sinif=""):
        """Adını kendisi yazarak girmiş (listede olmayan) öğrenciye numara verir; ilerlemesi yeni kayda taşınır."""
        r = self.db.tek("SELECT * FROM ogrenci WHERE anahtar=? ORDER BY son DESC", (anahtar,))
        if not r or anahtar.startswith("#"):
            raise Hata(404, "Numarasız öğrenci bulunamadı.")
        with self.db.toplu():
            k = self.kayit_ekle(r["ad"], sinif, robot=r["robot"])
            self.db.yap("INSERT OR REPLACE INTO esleme (anahtar, pid, kayit_id) VALUES (?,?,?)", (anahtar, r.get("pid") or "", k["id"]))
            self._tasi(anahtar, "#%d" % k["id"])
        self.gunluk("Numara verildi: %s -> %s" % (r["ad"], k["no"]))
        return k

    def birlestir(self, kaynak, hedef_id):
        """kaynak öğrencinin (numarasız ya da listedeki başka bir kayıt) bütün ilerlemesini hedef kayda ekler ve kaynağı kaldırır."""
        hedef = self.kayit_bul(kid=hedef_id)
        if not hedef:
            raise Hata(404, "Hedef öğrenci bulunamadı.")
        yeni = "#%d" % hedef["id"]
        if kaynak == yeni:
            raise Hata(400, "Öğrenci kendisiyle birleştirilemez.")
        with self.db.toplu():
            if kaynak.startswith("#"):
                k2 = self.kayit_bul(kid=kaynak[1:]) if kaynak[1:].isdigit() else None
                if not k2:
                    raise Hata(404, "Kaynak öğrenci bulunamadı.")
                self.db.yap("UPDATE esleme SET kayit_id=? WHERE kayit_id=?", (hedef["id"], k2["id"]))
                self._tasi(kaynak, yeni)
                self.db.yap("DELETE FROM kayit WHERE id=?", (k2["id"],))
                ad = k2["ad"]
            else:
                r = self.db.tek("SELECT * FROM ogrenci WHERE anahtar=? ORDER BY son DESC", (kaynak,))
                if not r:
                    raise Hata(404, "Kaynak öğrenci bulunamadı.")
                self.db.yap("INSERT OR REPLACE INTO esleme (anahtar, pid, kayit_id) VALUES (?,?,?)", (kaynak, r.get("pid") or "", hedef["id"]))
                self._tasi(kaynak, yeni)
                ad = r["ad"]
            self.db.yap("UPDATE ogrenci SET ad=? WHERE anahtar=?", (hedef["ad"], yeni))
        self.gunluk("Birleştirildi: %s -> %s (no %s)" % (ad, hedef["ad"], hedef["no"]))
        return {"ok": True}

    def ilerleme_sifirla(self, anahtar):
        """Öğrencinin yıldızlarını ve bloklarını siler. Öğrencinin bilgisayarında kalan eski kayıt da bir sonraki bağlantıda silinir."""
        if not self.db.tek("SELECT 1 AS v FROM ogrenci WHERE anahtar=?", (anahtar,)) and not (anahtar.startswith("#") and self.kayit_bul(kid=anahtar[1:])):
            raise Hata(404, "Öğrenci bulunamadı.")
        an = simdi()
        with self.db.toplu():
            uyglar = {r["uygulama"] for r in self.db.sorgu("SELECT uygulama FROM ogrenci WHERE anahtar=? UNION SELECT uygulama FROM ilerleme WHERE anahtar=?", (anahtar, anahtar))} or {"afi-kod"}
            for uyg in uyglar:
                self.db.yap("INSERT OR REPLACE INTO ilerleme (anahtar, uygulama, veri, guncelleme) VALUES (?,?,?,?)",
                            (anahtar, uyg, json.dumps({"stars": {}, "ws": {}, "seen": {}, "sifir": an}), an))
            for t in ("anlik", "olay", "gunluk"):
                self.db.yap("DELETE FROM " + t + " WHERE anahtar=?", (anahtar,))
            self.db.yap("UPDATE ogrenci SET yildiz=0, biten=0, sure=0, adim_hata=0, sifir=? WHERE anahtar=?", (an, anahtar))
        return {"ok": True}

    # ------------------------------------------------------------ ses, komutlar, bilgisayarlar
    def ses_genel(self):
        return "kapali" if self.db.ayar("ses") == "kapali" else "acik"

    def ses_durum(self, anahtar=None):
        """Öğrencinin afi kod seslerinin durumu: öğrenciye özel ayar varsa o, yoksa sınıfın genel ayarı."""
        if anahtar:
            r = self.db.tek("SELECT deger FROM ses_ayar WHERE anahtar=?", (anahtar,))
            if r and r["deger"] in ("acik", "kapali"):
                return r["deger"]
        return self.ses_genel()

    def ses_yaz(self, kullanici, hedef, deger):
        """hedef "*": herkes (öğrenciye özel ayarlar da kalkar); "sinif:X": o sınıftaki öğrenciler; yoksa tek öğrencinin anahtarı.
        deger: "acik" / "kapali"; tek öğrencide None verilirse sınıfın genel ayarına döner."""
        if deger not in ("acik", "kapali", None):
            raise Hata(400, "Ses ayarı açık ya da kapalı olmalı.")
        with self.db.toplu():
            if hedef == "*":
                if deger is None:
                    raise Hata(400, "Ses ayarı açık ya da kapalı olmalı.")
                self.db.ayar_yaz("ses", deger)
                self.db.yap("DELETE FROM ses_ayar")
            elif str(hedef).startswith("sinif:"):
                for k in self.db.sorgu("SELECT id FROM kayit WHERE sinif=?", (hedef[6:],)):
                    self._ses_ogrenci("#%d" % k["id"], deger)
            else:
                self._ses_ogrenci(str(hedef), deger)
        self.gunluk("Ses: %s -> %s (%s)" % (hedef, deger or "sınıfla aynı", kullanici["kullanici"]))
        return {"ok": True, "ses": self.ses_genel()}

    def _ses_ogrenci(self, anahtar, deger):
        if deger is None or deger == self.ses_genel():
            self.db.yap("DELETE FROM ses_ayar WHERE anahtar=?", (anahtar,))
        else:
            self.db.yap("INSERT OR REPLACE INTO ses_ayar (anahtar, deger) VALUES (?,?)", (anahtar, deger))

    def komut_gonder(self, kullanici, hedef, komut):
        if komut not in KOMUTLAR:
            raise Hata(400, "Bilinmeyen komut.")
        r = self.mesaj_gonder(kullanici, hedef or "*", komut, "komut")
        self.gunluk("Komut: %s -> %s (%s)" % (komut, hedef or "*", kullanici["kullanici"]))
        return r

    def _mesajlar(self, son_id, hedefler, ip):
        """son_id'den sonraki, bu hedeflere giden mesajlar. Herkese giden mesaj, gönderen öğretmenin ağ aralığı dışındaki bilgisayarlara gitmez."""
        out = []
        soru = ",".join("?" * len(hedefler))
        for ms in self.db.sorgu("SELECT * FROM mesaj WHERE id>? AND hedef IN (%s) ORDER BY id" % soru, (son_id,) + tuple(hedefler)):
            araliklar = json.loads(ms["araliklar"] or "[]")
            if ms["hedef"] in ("*",) and araliklar and not ortak.aralikta(ip, araliklar):
                continue
            out.append({"id": ms["id"], "metin": ms["metin"], "tur": ms["tur"], "gonderen": ms["gonderen"], "zaman": ms["zaman"]})
        return out

    def cihaz_gor(self, cid, ip, ad="", anahtar=""):
        """Bağlı bilgisayarları (misafir olarak çalışanlar dahil) bellekte tutar; panelde sayıları görünür."""
        cid = str(cid or "")[:40]
        if not cid:
            return
        with self.kilit:
            self.cihazlar[cid] = {"ip": ip, "ad": str(ad or "")[:60], "son": simdi(), "anahtar": anahtar}
            if len(self.cihazlar) > 2000:
                for k in sorted(self.cihazlar, key=lambda k: self.cihazlar[k]["son"])[:500]:
                    self.cihazlar.pop(k, None)

    def cihaz(self, v, ip):
        """Öğrenci girmemişken (misafir ya da giriş ekranı) uygulamanın bağlantısı: ses ayarı, herkese giden mesajlar ve komutlar."""
        cid = str(v.get("cid") or "")[:40]
        self.cihaz_gor(cid, ip, (v.get("cihaz") or {}).get("ad") or ip_adi(ip))
        en_son = self.db.tek("SELECT MAX(id) AS m FROM mesaj")["m"] or 0
        try:
            son = int(v.get("son") or 0)
        except (TypeError, ValueError):
            son = 0
        ilk = v.get("son") in (None, "") or son > en_son          # ilk bağlantı (ya da veriler silinmiş): eski mesajlar gelmez
        mesajlar = [] if ilk else self._mesajlar(son, ["*", "cihaz:" + cid], ip)
        return {"ok": True, "ses": self.ses_genel(), "mesajlar": mesajlar, "son": en_son, "kip": self.giris_kipi(), "surum": self.paketler.aktif(str(v.get("uygulama") or "afi-kod")[:40])[0]}

    def bu_bilgisayar(self, ip, cihaz_adi="", uyg="afi-kod"):
        """Bu bilgisayardan (aynı IP ya da aynı bilgisayar adı) son 90 günde giren öğrenciler.
        Bilgisayardaki tarayıcı kayıtları silinse ya da adres değişse bile öğrenci adını listede bulur."""
        if self.giris_kipi() == "numara":
            return {"ogrenciler": []}
        adlar = {a for a in (str(cihaz_adi or "")[:60], ip_adi(ip)) if a}
        sinir = simdi() - 90 * 86400
        out, gorulen = [], set()
        for r in self.db.sorgu("SELECT anahtar, ad, robot, ip, cihaz, son FROM ogrenci WHERE uygulama=? AND son>? ORDER BY son DESC LIMIT 400", (uyg, sinir)):
            if r["anahtar"] in gorulen or not (r["ip"] == ip or (r["cihaz"] and r["cihaz"] in adlar)):
                continue
            gorulen.add(r["anahtar"])
            k = self.kayit_bul(kid=r["anahtar"][1:]) if r["anahtar"].startswith("#") and r["anahtar"][1:].isdigit() else None
            if r["anahtar"].startswith("#") and not k:
                continue
            out.append({"ad": k["ad"] if k else r["ad"], "robot": r["robot"] or "afi", "kayit": k["id"] if k else None, "son": r["son"]})
            if len(out) >= 40:
                break
        return {"ogrenciler": out}

    # ------------------------------------------------------------ öğrenci tarafı
    def nabiz(self, v, ip):
        uyg = str(v.get("uygulama") or "afi-kod")[:40]
        ogr = v.get("ogrenci") or {}
        anahtar, k = self.kimlik_coz(ogr)
        ad = (k["ad"] if k else str(ogr.get("ad") or "").strip())[:40]
        if not ad:
            raise Hata(400, "Öğrenci adı yok.")
        kip = self.giris_kipi()
        if not k and kip == "numara":
            return {"ok": False, "giris_gerekli": True, "kip": kip, "mesajlar": [], "surum": self.paketler.aktif(uyg)[0]}
        robot = str(ogr.get("robot") or (k["robot"] if k else "") or "afi")[:20]
        pid = str(ogr.get("pid") or "")[:40]
        cihaz = v.get("cihaz") or {}
        adim = v.get("adim") or {}
        adim_id = str(adim.get("id") or "")[:40]
        ip = str(cihaz.get("ip") or ip) if cihaz.get("istemci") and ip.startswith("127.") else ip
        simd = simdi()
        try:
            bos = max(0.0, float(v.get("bos") or 0))
        except (TypeError, ValueError):
            bos = 0.0
        with self.db.toplu():
            if k and ogr.get("robot") and robot != (k["robot"] or "afi"):      # öğrencinin seçtiği robot bütün bilgisayarlarda aynı görünür
                self.db.yap("UPDATE kayit SET robot=?, guncelleme=? WHERE id=?", (robot, simd, k["id"]))
                k["robot"] = robot
            m = self.db.tek("SELECT * FROM ogrenci WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
            if m is None:
                son_id = (self.db.tek("SELECT MAX(id) AS m FROM mesaj")["m"] or 0)
                self.db.yap("INSERT INTO ogrenci (anahtar, uygulama, ad, robot, ilk, son, son_mesaj) VALUES (?,?,?,?,?,?,?)", (anahtar, uyg, ad, robot, simd, None, son_id))
                m = {"son_mesaj": son_id}
                self.gunluk("Yeni öğrenci: " + ad + " (" + ip + ")")
            son_mesaj = m.get("son_mesaj") or 0
            # Aynı ad ve aynı robotla, aynı anda iki ayrı bilgisayardan bağlanan numarasız öğrenci: kayıtları karışır, öğretmene bildirilir.
            cakisma = m.get("cakisma")
            if not k and pid and m.get("pid") and m["pid"] != pid and m.get("ip") and m["ip"] != ip and m.get("son") and simd - m["son"] < 25:
                cakisma = simd
            dt = simd - (m.get("son") or 0)
            ekle = dt if (0 < dt <= SURE_ARALIK and bos < BOS_SN) else 0.0
            degisti = adim_id != (m.get("adim") or "")
            adim_bas = simd if (degisti or not m.get("adim_bas")) else m["adim_bas"]
            adim_hata = 0 if degisti else int(m.get("adim_hata") or 0)
            yardim = m.get("yardim")
            basari = hata = 0
            try:
                saat = float(v.get("saat") or 0)       # öğrenci bilgisayarının saati (gönderim anı)
            except (TypeError, ValueError):
                saat = 0
            for o in (v.get("olaylar") or [])[:60]:
                tur = str(o.get("tur") or "")[:20]
                try:
                    zaman = float(o.get("zaman") or simd)
                except (TypeError, ValueError):
                    zaman = simd
                if saat:        # öğrenci bilgisayarının saati yanlış olabilir: olayın ne kadar önce olduğuna bakılır, sunucu saatine çevrilir
                    zaman = simd - min(max(saat - zaman, 0.0), 30 * 86400.0)
                o_adim = str(o.get("adim") or "")[:40]
                if tur == "yardim":
                    yardim = zaman
                elif tur == "yardim-iptal":
                    yardim = None
                elif tur == "hata":
                    hata += 1
                    if o_adim == adim_id and zaman >= adim_bas - 5:
                        adim_hata += 1
                elif tur == "basari":
                    basari += 1
                    if o_adim == adim_id:
                        adim_hata = 0
                self.db.yap("INSERT INTO olay (zaman, anahtar, uygulama, tur, adim, ayrinti) VALUES (?,?,?,?,?,?)",
                            (zaman, anahtar, uyg, tur, o_adim, json.dumps(o.get("ayrinti"), ensure_ascii=False)[:500]))
            son = (simd - CEVRIMICI_SN - 1) if v.get("cikis") else simd       # sayfa kapanırken gelen son nabız: hemen "bağlı değil" görünür
            # Yıldız ve biten adım sayısı sunucudaki kayıttan hesaplanır (öğrenci başka bilgisayara geçtiğinde ekrandaki sayı düşmesin).
            il = self.db.tek("SELECT veri FROM ilerleme WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
            yildiz, biten = self._ozet(json.loads(il["veri"])) if il else (int(v.get("yildiz") or 0), int(v.get("biten") or 0))
            self.db.yap("UPDATE ogrenci SET ad=?, robot=?, ip=?, cihaz=?, istemci=?, oturum=?, pid=?, son=?, adim=?, adim_ad=?, durum=?, yildiz=?, biten=?, "
                        "adim_bas=?, adim_hata=?, adim_yildiz=?, bos=?, sure=COALESCE(sure, 0)+?, yardim=?, cakisma=? WHERE anahtar=? AND uygulama=?",
                        (ad, robot, ip, str(cihaz.get("ad") or ip_adi(ip) or "")[:60], 1 if cihaz.get("istemci") else 0, str(cihaz.get("kullanici") or "")[:60], pid or m.get("pid"), son,
                         adim_id, str(adim.get("ad") or "")[:120], str(v.get("durum") or "")[:20], yildiz, biten,
                         adim_bas, adim_hata, int(adim.get("yildiz") or 0), bos, ekle, yardim, cakisma, anahtar, uyg))
            gun = time.strftime("%Y-%m-%d", time.localtime(simd))
            self.db.yap("INSERT OR IGNORE INTO gunluk (anahtar, uygulama, gun, ilk, son) VALUES (?,?,?,?,?)", (anahtar, uyg, gun, simd, simd))
            self.db.yap("UPDATE gunluk SET sure=sure+?, basari=basari+?, hata=hata+?, son=? WHERE anahtar=? AND uygulama=? AND gun=?", (ekle, basari, hata, simd, anahtar, uyg, gun))
            cid = str(v.get("cid") or "")[:40]
            hedefler = ["*", anahtar] + (["sinif:" + k["sinif"]] if k and k["sinif"] else []) + (["cihaz:" + cid] if cid else [])
            mesajlar = self._mesajlar(son_mesaj, hedefler, ip)
            en_son = self.db.tek("SELECT MAX(id) AS m FROM mesaj")["m"] or 0
            if en_son > son_mesaj:
                self.db.yap("UPDATE ogrenci SET son_mesaj=? WHERE anahtar=? AND uygulama=?", (en_son, anahtar, uyg))
        self.cihaz_gor(v.get("cid"), ip, cihaz.get("ad") or ip_adi(ip), anahtar)
        surum = self.paketler.aktif(uyg)[0]
        return {"ok": True, "mesajlar": mesajlar, "surum": surum, "anahtar": anahtar, "kimlik": self.kimlik_bilgi(k), "kip": kip, "ses": self.ses_durum(anahtar),
                "yardim": bool(yardim), "cakisma": bool(cakisma and simd - cakisma < 60), "sifir": m.get("sifir") or 0}

    def ilerleme_yaz(self, v):
        uyg = str(v.get("uygulama") or "afi-kod")[:40]
        anahtar, k = self.kimlik_coz(v.get("ogrenci"))
        if anahtar.startswith("|"):
            raise Hata(400, "Öğrenci adı yok.")
        if not k and self.giris_kipi() == "numara":
            raise Hata(403, "Numarayla giriş gerekli.")
        with self.db.toplu():
            r = self.db.tek("SELECT veri FROM ilerleme WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
            birlesik = ilerleme_birlestir(json.loads(r["veri"]) if r else {}, v.get("veri") or {})
            istek = birlesik.pop("sifirla", None)
            if istek:                                 # öğrenci kendi kaydını sıfırladı: sunucu saatiyle işlenir, öğretmen olaylarda görür
                birlesik["sifir"] = simdi()
                birlesik["sifirla_son"] = istek       # aynı istek yeniden gelirse ikinci kez sıfırlanmaz
                self.db.yap("INSERT INTO olay (zaman, anahtar, uygulama, tur, adim, ayrinti) VALUES (?,?,?,?,?,?)", (simdi(), anahtar, uyg, "sifirla", "", "null"))
                self.db.yap("UPDATE ogrenci SET adim_hata=0 WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
            self.db.yap("INSERT OR REPLACE INTO ilerleme (anahtar, uygulama, veri, guncelleme) VALUES (?,?,?,?)", (anahtar, uyg, json.dumps(birlesik, ensure_ascii=False), simdi()))
            self.db.yap("UPDATE ogrenci SET yildiz=?, biten=? WHERE anahtar=? AND uygulama=?", self._ozet(birlesik) + (anahtar, uyg))
        return {"ok": True, "veri": birlesik}

    def ilerleme_oku(self, uyg, ogr, robot=None):
        if not isinstance(ogr, dict):          # eski çağrı biçimi: (uygulama, ad, robot)
            ogr = {"ad": ogr, "robot": robot or "afi"}
        anahtar, k = self.kimlik_coz(ogr)
        r = self.db.tek("SELECT veri, guncelleme FROM ilerleme WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
        return {"veri": json.loads(r["veri"]) if r else None, "guncelleme": r["guncelleme"] if r else None, "kimlik": self.kimlik_bilgi(k)}

    def kimlik_tasi(self, v):
        """Numarasız öğrenci robotunu değiştirince kayıtları yeni kimliğe (ad + yeni robot) taşınır.
        Numaralı öğrencide kimlik değişmez; yalnızca robot seçimi kaydedilir."""
        uyg = str(v.get("uygulama") or "afi-kod")[:40]
        e, y = v.get("eski") or {}, v.get("yeni") or {}
        eski, ke = self.kimlik_coz(e)
        yeni, ky = self.kimlik_coz(y)
        if ky:
            self.db.yap("UPDATE kayit SET robot=?, guncelleme=? WHERE id=?", (str(y.get("robot") or "afi")[:20], simdi(), ky["id"]))
            self.db.yap("UPDATE ogrenci SET robot=? WHERE anahtar=?", (str(y.get("robot") or "afi")[:20], yeni))
            return {"ok": True}
        if eski == yeni or eski.startswith("|") or yeni.startswith("|") or ke:
            return {"ok": True}
        pid = str(y.get("pid") or "")
        hedef = self.db.tek("SELECT pid, son FROM ogrenci WHERE anahtar=? AND uygulama=?", (yeni, uyg))
        if hedef and pid and hedef.get("pid") and hedef["pid"] != pid:
            # Bu ad ve bu robotla başka bir öğrenci var: ikisinin kaydı birbirine karışmasın.
            return {"ok": False, "dolu": True}
        with self.db.toplu():
            self._tasi(eski, yeni)
            self.db.yap("UPDATE ogrenci SET robot=? WHERE anahtar=? AND uygulama=?", (str(y.get("robot") or "afi")[:20], yeni, uyg))
        return {"ok": True}

    def anlik_yaz(self, v):
        uyg = str(v.get("uygulama") or "afi-kod")[:40]
        anahtar, k = self.kimlik_coz(v.get("ogrenci"))
        if anahtar.startswith("|") or (not k and self.giris_kipi() == "numara"):
            return {"ok": False}
        ws = v.get("ws")
        self.db.yap("INSERT OR REPLACE INTO anlik (anahtar, uygulama, adim, ws, kod, guncelleme) VALUES (?,?,?,?,?,?)",
                    (anahtar, uyg, str(v.get("adim") or "")[:40], json.dumps(ws, ensure_ascii=False)[:400000] if ws is not None else None, str(v.get("kod") or "")[:20000], simdi()))
        return {"ok": True}

    # ------------------------------------------------------------ öğretmen tarafı
    BOS_SATIR = {"ip": "", "cihaz": "", "istemci": 0, "oturum": "", "ilk": None, "son": None, "adim": "", "adim_ad": "", "durum": "", "yildiz": 0, "biten": 0,
                 "adim_bas": None, "adim_hata": 0, "adim_yildiz": 0, "bos": 0, "sure": 0, "yardim": None, "cakisma": None}

    def sinif(self, kullanici, uyg=None):
        """Sınıf listesindeki bütün öğrenciler (hiç bağlanmamış olanlar da) ve listede olmayan numarasız öğrenciler."""
        uyg = uyg or "afi-kod"
        simd = simdi()
        satirlar = {r["anahtar"]: r for r in self.db.sorgu("SELECT * FROM ogrenci WHERE uygulama=?", (uyg,))}
        bugun = {r["anahtar"]: r for r in self.db.sorgu("SELECT anahtar, sure, basari, hata FROM gunluk WHERE uygulama=? AND gun=?", (uyg, time.strftime("%Y-%m-%d", time.localtime(simd))))}
        genel = self.ses_genel()
        sesler = {r["anahtar"]: r["deger"] for r in self.db.sorgu("SELECT anahtar, deger FROM ses_ayar")}

        def hazirla(r, k):
            r.pop("son_mesaj", None)
            r.pop("pid", None)
            r["kayit"] = k["id"] if k else None
            r["no"] = k["no"] if k else ""
            r["sinif"] = (k["sinif"] or "") if k else ""
            r["notu"] = (k["notu"] or "") if k else ""
            r["cevrimici"] = bool(r["son"] and simd - r["son"] < CEVRIMICI_SN)
            r["cakisma"] = bool(r.get("cakisma") and simd - r["cakisma"] < 600)
            g = bugun.get(r["anahtar"]) or {}
            r["bugun"] = {"sure": round(g.get("sure") or 0), "basari": g.get("basari") or 0, "hata": g.get("hata") or 0}
            r["ses"] = sesler.get(r["anahtar"], genel)
            r["ses_ozel"] = r["anahtar"] in sesler
            return r
        out = []
        for k in self.db.sorgu("SELECT * FROM kayit"):
            a = "#%d" % k["id"]
            r = satirlar.pop(a, None)
            if r is None:
                r = dict(self.BOS_SATIR, anahtar=a, uygulama=uyg)
            elif not self.gorebilir(kullanici, r["ip"] or "") and r["ip"]:
                continue
            r["ad"], r["robot"] = k["ad"], (r.get("robot") or k["robot"] or "afi")
            out.append(hazirla(r, k))
        for a, r in satirlar.items():
            if a.startswith("#") or not self.gorebilir(kullanici, r["ip"] or ""):
                continue
            out.append(hazirla(r, None))
        out.sort(key=lambda r: (r["sinif"].lower(), ortak.anahtar_yap(r["ad"], "")))
        return out

    def siniflar(self):
        return sorted({(r["sinif"] or "") for r in self.db.sorgu("SELECT DISTINCT sinif FROM kayit")} - {""}, key=lambda x: x.lower())

    def _gorulebilir(self, kullanici, anahtar, uyg):
        r = self.db.tek("SELECT * FROM ogrenci WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
        k = self.kayit_bul(kid=anahtar[1:]) if anahtar.startswith("#") and anahtar[1:].isdigit() else None
        if not r and not k:
            raise Hata(404, "Öğrenci bulunamadı.")
        if r and r["ip"] and not self.gorebilir(kullanici, r["ip"]):
            raise Hata(404, "Öğrenci bulunamadı.")
        return r, k

    def ogrenci_ayrinti(self, kullanici, uyg, anahtar):
        r, k = self._gorulebilir(kullanici, anahtar, uyg)
        simd = simdi()
        if r is None:
            r = dict(self.BOS_SATIR, anahtar=anahtar, uygulama=uyg, ad=k["ad"], robot=k["robot"] or "afi")
        il = self.db.tek("SELECT veri FROM ilerleme WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
        an = self.db.tek("SELECT adim, ws, kod, guncelleme FROM anlik WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
        olaylar = self.db.sorgu("SELECT zaman, tur, adim, ayrinti FROM olay WHERE anahtar=? AND uygulama=? ORDER BY id DESC LIMIT 80", (anahtar, uyg))
        # adım adım: kaç kez denedi, kaç kez hata aldı, ne zaman başardı
        adimlar = {x["adim"]: {"hata": x["h"] or 0, "basari": x["b"] or 0, "ilk": x["ilk"], "son": x["son"]} for x in self.db.sorgu(
            "SELECT adim, SUM(tur='hata') AS h, SUM(tur='basari') AS b, MIN(zaman) AS ilk, MAX(zaman) AS son FROM olay WHERE anahtar=? AND uygulama=? AND tur IN ('hata','basari') GROUP BY adim", (anahtar, uyg))}
        # en sık aldığı hata mesajları
        sayac = {}
        for x in self.db.sorgu("SELECT ayrinti FROM olay WHERE anahtar=? AND uygulama=? AND tur='hata' ORDER BY id DESC LIMIT 400", (anahtar, uyg)):
            try:
                ms = (json.loads(x["ayrinti"]) or {}).get("mesaj")
            except (ValueError, AttributeError):
                ms = None
            if ms:
                sayac[ms] = sayac.get(ms, 0) + 1
        hatalar = [{"mesaj": ms, "sayi": n} for ms, n in sorted(sayac.items(), key=lambda x: -x[1])[:6]]
        gunler = self.db.sorgu("SELECT gun, sure, basari, hata, ilk, son FROM gunluk WHERE anahtar=? AND uygulama=? ORDER BY gun DESC LIMIT 40", (anahtar, uyg))
        veri = json.loads(il["veri"]) if il else {}
        r.pop("son_mesaj", None)
        r.pop("pid", None)
        r["cevrimici"] = bool(r["son"] and simd - r["son"] < CEVRIMICI_SN)
        r["cakisma"] = bool(r.get("cakisma") and simd - r["cakisma"] < 600)
        if k:
            r.update({"ad": k["ad"], "kayit": k["id"], "no": k["no"], "sinif": k["sinif"] or "", "notu": k["notu"] or ""})
        else:
            r.update({"kayit": None, "no": "", "sinif": "", "notu": ""})
        r["ses"] = self.ses_durum(anahtar)
        r["ses_ozel"] = bool(self.db.tek("SELECT 1 AS v FROM ses_ayar WHERE anahtar=?", (anahtar,)))
        return {"ogrenci": r, "simdi": simd, "yildizlar": veri.get("stars") or {}, "adimlar": adimlar, "hatalar": hatalar, "gunler": gunler,
                "anlik": {"adim": an["adim"], "ws": json.loads(an["ws"]) if an["ws"] else None, "kod": an["kod"], "guncelleme": an["guncelleme"]} if an else None,
                "olaylar": olaylar}

    def rapor(self, kullanici, uyg, sinif_adi=None):
        """Sınıf raporu: öğrenci özetleri, en çok zorlanılan adımlar, gün gün katılım."""
        uyg = uyg or "afi-kod"
        def uygun(o):         # "*": herkes, "-": numarasızlar, "~": listede olup sınıfı yazılmamışlar, yoksa sınıf adı
            if sinif_adi in (None, "", "*"):
                return True
            if sinif_adi == "-":
                return not o["kayit"]
            if sinif_adi == "~":
                return bool(o["kayit"]) and not o["sinif"]
            return bool(o["kayit"]) and o["sinif"] == sinif_adi
        ogr = [o for o in self.sinif(kullanici, uyg) if uygun(o)]
        anahtarlar = {o["anahtar"] for o in ogr}
        adim = {}
        for x in self.db.sorgu("SELECT anahtar, adim, SUM(tur='hata') AS h, SUM(tur='basari') AS b FROM olay WHERE uygulama=? AND tur IN ('hata','basari') GROUP BY anahtar, adim", (uyg,)):
            if x["anahtar"] not in anahtarlar or not x["adim"]:
                continue
            a = adim.setdefault(x["adim"], {"adim": x["adim"], "hata": 0, "basari": 0, "deneyen": 0, "basaran": 0})
            a["hata"] += x["h"] or 0
            a["basari"] += x["b"] or 0
            a["deneyen"] += 1
            a["basaran"] += 1 if x["b"] else 0
        zor = sorted([a for a in adim.values() if a["hata"]], key=lambda a: (-(a["hata"] / max(1, a["deneyen"])), -a["hata"]))[:15]
        gun = {}
        toplam = {}
        for x in self.db.sorgu("SELECT anahtar, gun, sure, basari, hata FROM gunluk WHERE uygulama=?", (uyg,)):
            if x["anahtar"] not in anahtarlar:
                continue
            g = gun.setdefault(x["gun"], {"gun": x["gun"], "ogrenci": 0, "sure": 0, "basari": 0, "hata": 0})
            g["ogrenci"] += 1
            g["sure"] += x["sure"] or 0
            g["basari"] += x["basari"] or 0
            g["hata"] += x["hata"] or 0
            t = toplam.setdefault(x["anahtar"], {"gun": 0, "hata": 0, "basari": 0})
            t["gun"] += 1
            t["hata"] += x["hata"] or 0
            t["basari"] += x["basari"] or 0
        for o in ogr:
            o["toplam"] = toplam.get(o["anahtar"]) or {"gun": 0, "hata": 0, "basari": 0}
        return {"ogrenciler": ogr, "zor_adimlar": zor, "gunler": sorted(gun.values(), key=lambda g: g["gun"], reverse=True)[:60], "simdi": simdi(), "siniflar": self.siniflar()}

    def yardim_kapat(self, kullanici, uyg, anahtar):
        self._gorulebilir(kullanici, anahtar, uyg)
        self.db.yap("UPDATE ogrenci SET yardim=NULL WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
        return {"ok": True}

    def mesaj_gonder(self, kullanici, hedef, metin, tur="mesaj"):
        metin = str(metin or "").strip()[:500]
        if not metin and tur == "mesaj":
            raise Hata(400, "Mesaj boş.")
        araliklar = json.loads(kullanici.get("araliklar") or "[]") if kullanici["rol"] != "admin" else []
        mid = self.db.yap("INSERT INTO mesaj (hedef, araliklar, metin, tur, gonderen, zaman) VALUES (?,?,?,?,?,?)",
                          (hedef or "*", json.dumps(araliklar), metin, tur, kullanici["ad"], simdi()))
        return {"ok": True, "id": mid}

    @staticmethod
    def _dk(sn):
        return int(round((sn or 0) / 60.0))

    @staticmethod
    def _tarih(t):
        return time.strftime("%d.%m.%Y %H:%M", time.localtime(t)) if t else ""

    def csv_uret(self, kullanici, uyg, sinif_adi=None):
        cikti = io.StringIO()
        y = csv.writer(cikti, delimiter=";")
        y.writerow(["Numara", "Ad", "Sınıf", "Robot", "Biten adım", "Toplam yıldız", "Şu anki adım", "Toplam süre (dk)", "Geldiği gün sayısı", "Toplam başarılı deneme",
                    "Toplam hatalı deneme", "Bugün süre (dk)", "Bugün biten", "Bugün hata", "Bilgisayar", "IP", "Windows kullanıcısı", "İlk görülme", "Son görülme", "Not"])
        for r in self.rapor(kullanici, uyg, sinif_adi)["ogrenciler"]:
            y.writerow([r["no"], r["ad"], r["sinif"], r["robot"], r["biten"], r["yildiz"], r["adim_ad"] or r["adim"], self._dk(r["sure"]), r["toplam"]["gun"], r["toplam"]["basari"],
                        r["toplam"]["hata"], self._dk(r["bugun"]["sure"]), r["bugun"]["basari"], r["bugun"]["hata"], r["cihaz"], r["ip"], r.get("oturum") or "",
                        self._tarih(r["ilk"]), self._tarih(r["son"]), r["notu"]])
        return "﻿" + cikti.getvalue()      # BOM: Excel Türkçe karakterleri doğru açsın

    def devam_csv(self, kullanici, uyg, sinif_adi=None):
        """Yoklama: hangi öğrenci hangi gün geldi, kaç dakika çalıştı."""
        ogr = {o["anahtar"]: o for o in self.rapor(kullanici, uyg, sinif_adi)["ogrenciler"]}
        cikti = io.StringIO()
        y = csv.writer(cikti, delimiter=";")
        y.writerow(["Tarih", "Numara", "Ad", "Sınıf", "Geliş", "Son görülme", "Çalışma süresi (dk)", "Başarılı deneme", "Hatalı deneme"])
        for g in self.db.sorgu("SELECT * FROM gunluk WHERE uygulama=? ORDER BY gun DESC, anahtar", (uyg or "afi-kod",)):
            o = ogr.get(g["anahtar"])
            if not o:
                continue
            y.writerow([".".join(reversed(g["gun"].split("-"))), o["no"], o["ad"], o["sinif"], time.strftime("%H:%M", time.localtime(g["ilk"])) if g["ilk"] else "",
                        time.strftime("%H:%M", time.localtime(g["son"])) if g["son"] else "", self._dk(g["sure"]), g["basari"], g["hata"]])
        return "﻿" + cikti.getvalue()

    def liste_csv(self):
        """Sınıf listesi: numara kartları ya da Excel için."""
        cikti = io.StringIO()
        y = csv.writer(cikti, delimiter=";")
        y.writerow(["Numara", "Ad", "Sınıf", "Not"])
        for k in sorted(self.db.sorgu("SELECT * FROM kayit"), key=lambda k: ((k["sinif"] or "").lower(), ortak.anahtar_yap(k["ad"], ""))):
            y.writerow([k["no"], k["ad"], k["sinif"] or "", k["notu"] or ""])
        return "﻿" + cikti.getvalue()

    # ------------------------------------------------------------ otomatik yedek
    def otomatik_yedek(self):
        """Günde bir kez veritabanının kopyasını kayıt klasöründeki 'yedek' klasörüne alır; en yeni 14 yedek saklanır."""
        try:
            klasor = os.path.join(self.veri, "yedek")
            os.makedirs(klasor, exist_ok=True)
            hedef = os.path.join(klasor, "afi-sinif-%s.db" % time.strftime("%Y%m%d"))
            if not os.path.exists(hedef):
                self.db.yedekle(hedef + ".tmp")
                os.replace(hedef + ".tmp", hedef)
                self.gunluk("Otomatik yedek alındı: " + hedef)
            eskiler = sorted(f for f in os.listdir(klasor) if f.startswith("afi-sinif-") and f.endswith(".db"))
            for f in eskiler[:-YEDEK_SAKLA]:
                os.remove(os.path.join(klasor, f))
            return hedef
        except (OSError, sqlite3.Error) as e:
            self.gunluk("Otomatik yedek alınamadı: " + repr(e))
            return None

    def _yedek_dongu(self):
        while True:
            self.otomatik_yedek()
            time.sleep(3 * 3600)

    # ------------------------------------------------------------ güncelleme
    def denetle(self):
        adres = self.guncelleme_adresi()
        uzak = ortak.http_json(adres + ("&" if "?" in adres else "?") + "t=" + str(int(simdi())), zaman_asimi=15, yerel=False)
        out = []
        for uyg, bilgi in (uzak.get("uygulamalar") or {}).items():
            yerel = self.paketler.aktif(uyg)[0]
            out.append({"uygulama": uyg, "ad": bilgi.get("ad", uyg), "uzak": bilgi.get("surum"), "yerel": yerel,
                        "yeni": bool(not yerel or ortak.daha_yeni(bilgi.get("surum"), yerel)), "notlar": bilgi.get("notlar"), "boyut": bilgi.get("boyut")})
        self.son_denetim = {"zaman": simdi(), "adres": adres, "uygulamalar": out, "platform": uzak.get("platform")}
        self.gunluk("Güncelleme denetlendi: " + ", ".join("%s %s->%s" % (x["uygulama"], x["yerel"], x["uzak"]) for x in out))
        return self.son_denetim

    def guncelle(self, uyg):
        adres = self.guncelleme_adresi()
        uzak = ortak.http_json(adres + ("&" if "?" in adres else "?") + "t=" + str(int(simdi())), zaman_asimi=15, yerel=False)
        bilgi = (uzak.get("uygulamalar") or {}).get(uyg)
        if not bilgi:
            raise Hata(404, "Bu uygulama güncelleme listesinde yok: " + uyg)
        zip_url = urllib.parse.urljoin(adres, bilgi["zip"])
        gecici = tempfile.mkdtemp(prefix="indir-", dir=self.veri)
        try:
            yol = os.path.join(gecici, "paket.zip")
            ortak.http_indir(zip_url, yol, zaman_asimi=120)
            m = self.paketler.kur(yol, beklenen_sha=bilgi.get("sha256"))
        finally:
            shutil.rmtree(gecici, ignore_errors=True)
        self.paketler.temizle(uyg, sakla=3)
        self.gunluk("Güncellendi: %s %s" % (uyg, m["surum"]))
        self._yenile_komutu(uyg, m["surum"])
        return m

    def _yenile_komutu(self, uyg, surum):
        self.db.yap("INSERT INTO mesaj (hedef, araliklar, metin, tur, gonderen, zaman) VALUES ('*', '[]', ?, 'surum', 'sistem', ?)", (uyg + " " + surum, simdi()))

    # ------------------------------------------------------------ çalıştırma
    def baslat(self, tarayici_ac=False):
        sunucu = self

        class Isleyici(SunucuIsleyici):
            pass
        Isleyici.app = sunucu
        httpd = ThreadingHTTPServer(("0.0.0.0", self.port), Isleyici)
        httpd.daemon_threads = True
        httpd.gunluk = None
        self.httpd = httpd
        return httpd

    def adresler(self):
        ipler = ortak.yerel_ipler()
        pr = "" if self.port == 80 else ":" + str(self.port)
        return ["http://" + ip + pr + "/" for ip in ipler], "http://" + ortak.bilgisayar_adi() + pr + "/"


# ======================================================================= HTTP
class SunucuIsleyici(ortak.TemelIsleyici):
    app = None

    # ---- oturum
    def oturum(self, zorunlu=True, rol=None):
        cerez = self.headers.get("Cookie") or ""
        belirtec = None
        for p in cerez.split(";"):
            k, _, v = p.strip().partition("=")
            if k == "afi_oturum":
                belirtec = v
        k = None
        if belirtec:
            o = self.app.db.tek("SELECT kullanici_id, bitis FROM oturum WHERE belirtec=?", (belirtec,))
            if o and o["bitis"] > simdi():
                k = self.app.db.tek("SELECT id, kullanici, ad, rol, araliklar FROM kullanici WHERE id=?", (o["kullanici_id"],))
        if zorunlu and not k:
            raise Hata(401, "Giriş yapılmamış.")
        if k and rol == "admin" and k["rol"] != "admin":
            raise Hata(403, "Bu işlem için admin olmak gerekir.")
        return k

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self._yonet("GET")

    def do_POST(self):
        self._yonet("POST")

    def do_DELETE(self):
        self._yonet("DELETE")

    def _yonet(self, yontem):
        try:
            parca = urllib.parse.urlsplit(self.path)
            yol, sorgu = parca.path, dict(urllib.parse.parse_qsl(parca.query))
            if yol.startswith("/api/"):
                return self._api(yontem, yol, sorgu)
            if yontem != "GET":
                raise Hata(405, "Yöntem desteklenmiyor.")
            return self._statik(yol)
        except Hata as h:
            self.hata_gonder(h.kod, h.mesaj)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:      # beklenmeyen hata: sunucu çökmesin, günlüğe yazılsın
            self.app.gunluk("HATA " + self.path + " " + repr(e))
            self.hata_gonder(500, "Sunucu hatası: " + str(e))

    # ---- dosyalar
    def _statik(self, yol):
        app = self.app
        if yol in ("/", ""):
            uyglar = app.paketler.uygulamalar()
            if len(uyglar) == 1:
                return self.yonlendir("/" + uyglar[0]["uygulama"] + "/")
            return self.gonder(200, portal_html(app, uyglar), "text/html; charset=utf-8")
        if yol == "/panel":
            return self.yonlendir("/panel/")
        if yol.startswith("/panel/"):
            return self.dosya_gonder(ortak.kaynak_yolu("panel"), yol[len("/panel/"):])
        parcalar = yol.lstrip("/").split("/", 1)
        uyg = parcalar[0]
        surum, klasor = app.paketler.aktif(uyg)
        if not klasor:
            raise Hata(404, "Bulunamadı.")
        if len(parcalar) == 1:
            return self.yonlendir("/" + uyg + "/")
        return self.dosya_gonder(klasor, parcalar[1])

    # ---- API
    def _api(self, yontem, yol, q):
        app = self.app
        ip = self.istemci_ip()
        a = yol[len("/api/v1/"):] if yol.startswith("/api/v1/") else None
        if a is None:
            raise Hata(404, "Bilinmeyen API.")
        J = self.json_gonder

        # -- herkese açık
        if a == "bilgi":
            return J({"sistem": ortak.SISTEM, "rol": "sunucu", "ad": app.ad, "platform": ortak.PLATFORM_SURUM, "bilgisayar": ortak.bilgisayar_adi(), "port": app.port,
                      "uygulamalar": [{k: u[k] for k in ("uygulama", "ad", "surum")} for u in app.paketler.uygulamalar()],
                      "kurulum_gerekli": app.kullanici_sayisi() == 0, "ip": ip, "giris_kipi": app.giris_kipi(), "ozellikler": ["numara", "yardim"]})
        if a == "nabiz" and yontem == "POST":
            return J(app.nabiz(self.json_govde(), ip))
        if a == "ilerleme" and yontem == "POST":
            return J(app.ilerleme_yaz(self.json_govde()))
        if a == "ilerleme" and yontem == "GET":
            return J(app.ilerleme_oku(q.get("uygulama", "afi-kod"), {"ad": q.get("ad", ""), "robot": q.get("robot", "afi"), "pid": q.get("pid", ""), "kayit": q.get("kayit")}))
        if a == "ogrenci-giris" and yontem == "POST":
            return J(app.ogrenci_giris(self.json_govde()))
        if a == "cihaz" and yontem == "POST":
            return J(app.cihaz(self.json_govde(), ip))
        if a == "bu-bilgisayar":
            return J(app.bu_bilgisayar(ip, q.get("cihaz", ""), q.get("uygulama", "afi-kod")))
        if a == "kimlik" and yontem == "POST":
            return J(app.kimlik_tasi(self.json_govde()))
        if a == "anlik" and yontem == "POST":
            return J(app.anlik_yaz(self.json_govde()))
        if a == "paket":
            return J({u["uygulama"]: {"surum": u["surum"], "sha256": u["sha256"], "boyut": u["boyut"], "ad": u["ad"]} for u in app.paketler.uygulamalar()})
        if a.startswith("paket/") and a.endswith(".zip"):
            uyg = a[len("paket/"):-4]
            s, _ = app.paketler.aktif(uyg)
            z = app.paketler.zip_yolu(uyg, s) if s else None
            if not z or not os.path.isfile(z):
                raise Hata(404, "Paket yok.")
            return self.dosya_gonder(os.path.dirname(z), os.path.basename(z))
        if a == "ben":
            k = self.oturum(zorunlu=False)
            return J({"giris": bool(k), "kullanici": k["kullanici"] if k else None, "ad": k["ad"] if k else None, "rol": k["rol"] if k else None,
                      "ogretmen": bool(k)})
        if a == "kurulum":
            if yontem == "GET":
                return J({"gerekli": app.kullanici_sayisi() == 0, "yerel": self.yerelden_mi()})
            if app.kullanici_sayisi() != 0:
                raise Hata(403, "Kurulum zaten yapılmış.")
            if not self.yerelden_mi():
                raise Hata(403, "İlk admin hesabı yalnızca sunucunun çalıştığı bilgisayardan oluşturulabilir.")
            v = self.json_govde()
            app.kullanici_ekle(v.get("kullanici"), v.get("ad"), v.get("sifre"), "admin", [])
            app.gunluk("Admin hesabı oluşturuldu: " + str(v.get("kullanici")))
            return self._giris_yap(v.get("kullanici"), v.get("sifre"))
        if a == "giris" and yontem == "POST":
            v = self.json_govde()
            return self._giris_yap(v.get("kullanici"), v.get("sifre"))
        if a == "cikis" and yontem == "POST":
            k = self.oturum(zorunlu=False)
            if k:
                app.db.yap("DELETE FROM oturum WHERE kullanici_id=? AND bitis<?", (k["id"], simdi()))
            return J({"ok": True}, basliklar={"Set-Cookie": "afi_oturum=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})

        # -- öğretmen
        k = self.oturum()
        if a == "sinif":
            simd = simdi()
            with app.kilit:
                acik = [c for c in app.cihazlar.values() if simd - c["son"] < CEVRIMICI_SN and app.gorebilir(k, c["ip"])]
            return J({"ogrenciler": app.sinif(k, q.get("uygulama")), "simdi": simd, "uygulamalar": app.paketler.uygulamalar(), "siniflar": app.siniflar(), "kip": app.giris_kipi(),
                      "ses": app.ses_genel(), "cihaz": {"bagli": len(acik), "misafir": len([c for c in acik if not c["anahtar"]])}})
        if a == "ogrenci" and yontem == "GET":
            return J(app.ogrenci_ayrinti(k, q.get("uygulama", "afi-kod"), q.get("anahtar", "")))
        if a == "ogrenci" and yontem == "DELETE":          # listede olmayan (numarasız) öğrenciyi sil
            app._gorulebilir(k, q.get("anahtar", ""), q.get("uygulama", "afi-kod"))
            app.gunluk("Numarasız öğrenci silindi: %s (%s)" % (q.get("anahtar", ""), k["kullanici"]))
            return J(app.numarasiz_sil(q.get("anahtar", "")))
        if a == "rapor":
            return J(app.rapor(k, q.get("uygulama", "afi-kod"), q.get("sinif")))
        if a == "mesaj" and yontem == "POST":
            v = self.json_govde()
            return J(app.mesaj_gonder(k, v.get("hedef") or "*", v.get("metin"), "mesaj"))
        if a == "ses" and yontem == "POST":
            v = self.json_govde()
            if v.get("hedef") not in (None, "*") and not str(v.get("hedef")).startswith("sinif:"):
                app._gorulebilir(k, str(v.get("hedef")), str(v.get("uygulama") or "afi-kod"))
            return J(app.ses_yaz(k, v.get("hedef") or "*", v.get("deger")))
        if a == "komut" and yontem == "POST":
            v = self.json_govde()
            if v.get("hedef") not in (None, "*") and not str(v.get("hedef")).startswith(("sinif:", "cihaz:")):
                app._gorulebilir(k, str(v.get("hedef")), str(v.get("uygulama") or "afi-kod"))
            return J(app.komut_gonder(k, v.get("hedef") or "*", str(v.get("komut") or "")))
        if a == "yardim-kapat" and yontem == "POST":
            v = self.json_govde()
            return J(app.yardim_kapat(k, str(v.get("uygulama") or "afi-kod"), str(v.get("anahtar") or "")))
        if a in ("disa-aktar.csv", "devam.csv", "liste.csv"):
            if a == "liste.csv":
                veri, ad = app.liste_csv(), "afi-sinif-listesi"
            elif a == "devam.csv":
                veri, ad = app.devam_csv(k, q.get("uygulama"), q.get("sinif")), "afi-yoklama"
            else:
                veri, ad = app.csv_uret(k, q.get("uygulama"), q.get("sinif")), "afi-sinif-raporu"
            return self.gonder(200, veri, "text/csv; charset=utf-8", {"Content-Disposition": "attachment; filename=\"%s-%s.csv\"" % (ad, time.strftime("%Y%m%d"))})
        # -- sınıf listesi: öğrenci ekleme, düzenleme, numara verme
        if a == "kayitlar" and yontem == "GET":
            return J({"kayitlar": [app.kimlik_bilgi(x) for x in app.db.sorgu("SELECT * FROM kayit")], "siniflar": app.siniflar(), "kip": app.giris_kipi()})
        if a == "kayitlar" and yontem == "POST":
            v = self.json_govde()
            if v.get("id"):
                kayit = app.kayit_guncelle(int(v["id"]), v)
            else:
                kayit = app.kayit_ekle(v.get("ad"), v.get("sinif"), no=v.get("no"), notu=v.get("notu"))
                app.gunluk("Öğrenci eklendi: %s (no %s, %s)" % (kayit["ad"], kayit["no"], k["kullanici"]))
            return J({"ok": True, "kimlik": app.kimlik_bilgi(kayit)})
        if a == "kayitlar" and yontem == "DELETE":
            return J(app.kayit_sil(int(q.get("id") or 0)))
        if a == "kayitlar/toplu" and yontem == "POST":
            v = self.json_govde()
            return J(app.toplu_ekle(v.get("metin"), v.get("sinif")))
        if a == "kayitlar/numara-ver" and yontem == "POST":
            v = self.json_govde()
            if v.get("anahtar") == "*":          # görünen bütün numarasız öğrencilere
                verilen = [app.kimlik_bilgi(app.numara_ver(o["anahtar"], v.get("sinif") or "")) for o in app.sinif(k, v.get("uygulama")) if not o["kayit"]]
                return J({"ok": True, "verilen": verilen})
            app._gorulebilir(k, str(v.get("anahtar") or ""), str(v.get("uygulama") or "afi-kod"))
            return J({"ok": True, "verilen": [app.kimlik_bilgi(app.numara_ver(str(v.get("anahtar") or ""), v.get("sinif") or ""))]})
        if a == "kayitlar/birlestir" and yontem == "POST":
            v = self.json_govde()
            return J(app.birlestir(str(v.get("kaynak") or ""), int(v.get("hedef") or 0)))
        if a == "kayitlar/sifirla" and yontem == "POST":
            v = self.json_govde()
            app._gorulebilir(k, str(v.get("anahtar") or ""), str(v.get("uygulama") or "afi-kod"))
            app.gunluk("İlerleme sıfırlandı: %s (%s)" % (v.get("anahtar"), k["kullanici"]))
            return J(app.ilerleme_sifirla(str(v.get("anahtar") or "")))
        if a == "giris-kipi" and yontem == "POST":
            v = self.json_govde()
            if v.get("kip") not in ("serbest", "numara"):
                raise Hata(400, "Giriş kipi serbest ya da numara olmalı.")
            app.db.ayar_yaz("giris_kipi", v["kip"])
            app.gunluk("Giriş kipi: %s (%s)" % (v["kip"], k["kullanici"]))
            return J({"ok": True, "kip": v["kip"]})
        if a == "sunucu" and yontem == "GET":
            adresler, ad_adresi = app.adresler()
            bilgi = {"ad": app.ad, "platform": ortak.PLATFORM_SURUM, "bilgisayar": ortak.bilgisayar_adi(), "port": app.port,
                     "baslangic": app.baslangic, "simdi": simdi(), "adresler": adresler, "ad_adresi": ad_adresi,
                     "uygulamalar": [{x: u[x] for x in ("uygulama", "ad", "surum")} for u in app.paketler.uygulamalar()],
                     "kurulum": bool(ortak.kurulum_bilgisi()), "program": ortak.program_klasoru(), "kapatilabilir": bool(app.kapat)}
            if k["rol"] == "admin":
                bilgi["veri_klasoru"] = app.veri
                try:
                    with open(app.gunluk_dosya, encoding="utf-8", errors="replace") as f:
                        bilgi["gunluk"] = f.readlines()[-40:]
                except OSError:
                    bilgi["gunluk"] = []
            return J(bilgi)
        if a == "sunucu/kapat" and yontem == "POST":
            self.oturum(rol="admin")
            if not app.kapat:
                raise Hata(400, "Bu sunucu buradan kapatılamaz.")
            app.gunluk("Sunucu panelden kapatıldı (" + k["kullanici"] + ")")
            J({"ok": True})
            threading.Timer(0.5, app.kapat).start()
            return None
        if a == "sifre" and yontem == "POST":
            v = self.json_govde()
            tam = app.db.tek("SELECT * FROM kullanici WHERE id=?", (k["id"],))
            if not parola_dogru(str(v.get("eski") or ""), tam["tuz"], tam["ozet"]):
                raise Hata(403, "Eski parola yanlış.")
            if len(str(v.get("yeni") or "")) < 6:
                raise Hata(400, "Yeni parola en az 6 karakter olmalı.")
            tuz, ozet = parola_ozet(str(v["yeni"]))
            app.db.yap("UPDATE kullanici SET tuz=?, ozet=? WHERE id=?", (tuz, ozet, k["id"]))
            return J({"ok": True})

        # -- admin
        self.oturum(rol="admin")
        if a == "kullanicilar" and yontem == "GET":
            return J([dict(r, araliklar=json.loads(r["araliklar"] or "[]")) for r in app.db.sorgu("SELECT id, kullanici, ad, rol, araliklar, olusturma FROM kullanici ORDER BY id")])
        if a == "kullanicilar" and yontem == "POST":
            v = self.json_govde()
            if v.get("id"):
                hedef = app.db.tek("SELECT * FROM kullanici WHERE id=?", (int(v["id"]),))
                if not hedef:
                    raise Hata(404, "Kullanıcı yok.")
                araliklar = [x.strip() for x in (v.get("araliklar") or []) if x and x.strip()]
                for x in araliklar:
                    if not ortak.aralik_gecerli(x):
                        raise Hata(400, "Ağ aralığı anlaşılmadı: " + x)
                rol = v.get("rol") if v.get("rol") in ("admin", "ogretmen") else hedef["rol"]
                if hedef["rol"] == "admin" and rol != "admin" and app.db.tek("SELECT COUNT(*) AS n FROM kullanici WHERE rol='admin'")["n"] < 2:
                    raise Hata(400, "En az bir admin kalmalı.")
                app.db.yap("UPDATE kullanici SET ad=?, rol=?, araliklar=? WHERE id=?", ((v.get("ad") or hedef["ad"])[:60], rol, json.dumps(araliklar), hedef["id"]))
                if v.get("sifre"):
                    if len(v["sifre"]) < 6:
                        raise Hata(400, "Parola en az 6 karakter olmalı.")
                    tuz, ozet = parola_ozet(v["sifre"])
                    app.db.yap("UPDATE kullanici SET tuz=?, ozet=? WHERE id=?", (tuz, ozet, hedef["id"]))
                    app.db.yap("DELETE FROM oturum WHERE kullanici_id=?", (hedef["id"],))
                return J({"ok": True})
            yid = app.kullanici_ekle(v.get("kullanici"), v.get("ad"), v.get("sifre"), v.get("rol") or "ogretmen", v.get("araliklar") or [])
            return J({"ok": True, "id": yid})
        if a == "kullanicilar" and yontem == "DELETE":
            yid = int(q.get("id") or 0)
            hedef = app.db.tek("SELECT * FROM kullanici WHERE id=?", (yid,))
            if not hedef:
                raise Hata(404, "Kullanıcı yok.")
            if hedef["id"] == k["id"]:
                raise Hata(400, "Kendi hesabını silemezsin.")
            app.db.yap("DELETE FROM oturum WHERE kullanici_id=?", (yid,))
            app.db.yap("DELETE FROM kullanici WHERE id=?", (yid,))
            return J({"ok": True})
        if a == "ayarlar":
            if yontem == "POST":
                v = self.json_govde()
                if "sunucu_adi" in v:
                    app.ad = str(v["sunucu_adi"] or "").strip()[:60] or app.ad
                    app.db.ayar_yaz("sunucu_adi", app.ad)
                if "guncelleme_adresi" in v:
                    adr = str(v["guncelleme_adresi"] or "").strip()
                    if adr and not adr.startswith(("http://", "https://")):
                        raise Hata(400, "Adres http:// ya da https:// ile başlamalı.")
                    app.db.ayar_yaz("guncelleme_adresi", adr or None)
            adresler, ad_adresi = app.adresler()
            return J({"sunucu_adi": app.ad, "guncelleme_adresi": app.guncelleme_adresi(), "varsayilan_guncelleme_adresi": ortak.GUNCELLEME_ADRESI,
                      "adresler": adresler, "ad_adresi": ad_adresi, "veri_klasoru": app.veri, "platform": ortak.PLATFORM_SURUM})
        if a == "guncelleme" and yontem == "GET":
            return J({"yerel": app.paketler.uygulamalar(), "son_denetim": app.son_denetim, "adres": app.guncelleme_adresi()})
        if a == "guncelleme/denetle" and yontem == "POST":
            try:
                return J(app.denetle())
            except (OSError, ValueError) as e:
                raise Hata(502, "Güncelleme sunucusuna ulaşılamadı: " + str(e))
        if a == "guncelleme/kur" and yontem == "POST":
            v = self.json_govde()
            try:
                m = app.guncelle(str(v.get("uygulama") or "afi-kod"))
            except ortak.PaketHatasi as e:
                raise Hata(400, str(e))
            except (OSError, ValueError) as e:
                raise Hata(502, "İndirme başarısız: " + str(e))
            return J({"ok": True, "manifest": m})
        if a == "guncelleme/sec" and yontem == "POST":
            v = self.json_govde()
            try:
                app.paketler.sec(str(v.get("uygulama")), str(v.get("surum")))
            except ortak.PaketHatasi as e:
                raise Hata(400, str(e))
            app.gunluk("Sürüm seçildi: %s %s" % (v.get("uygulama"), v.get("surum")))
            app._yenile_komutu(str(v.get("uygulama")), str(v.get("surum")))
            return J({"ok": True})
        if a == "guncelleme/yukle" and yontem == "POST":
            ham = self.govde()
            gecici = tempfile.mkdtemp(prefix="yukle-", dir=app.veri)
            try:
                yol = os.path.join(gecici, "paket.zip")
                with open(yol, "wb") as f:
                    f.write(ham)
                try:
                    m = app.paketler.kur(yol)
                except ortak.PaketHatasi as e:
                    raise Hata(400, str(e))
            finally:
                shutil.rmtree(gecici, ignore_errors=True)
            app.gunluk("Elle paket yüklendi: %s %s" % (m["uygulama"], m["surum"]))
            app._yenile_komutu(m["uygulama"], m["surum"])
            return J({"ok": True, "manifest": m})
        if a == "yedek":
            gecici = tempfile.mkdtemp(prefix="yedek-", dir=app.veri)
            try:
                yol = os.path.join(gecici, "afi-sinif-yedek.db")
                app.db.yedekle(yol)
                with open(yol, "rb") as f:
                    veri = f.read()
            finally:
                shutil.rmtree(gecici, ignore_errors=True)
            return self.gonder(200, veri, "application/octet-stream", {"Content-Disposition": "attachment; filename=\"afi-sinif-yedek-%s.db\"" % time.strftime("%Y%m%d-%H%M")})
        if a == "temizle" and yontem == "POST":
            v = self.json_govde()
            if v.get("onay") != "SİL":
                raise Hata(400, "Onay için SİL yazılmalı.")
            app.otomatik_yedek()                       # silmeden önce bugünün yedeği
            yedek = os.path.join(app.veri, "yedek", "silmeden-once-%s.db" % time.strftime("%Y%m%d-%H%M%S"))
            try:
                app.db.yedekle(yedek)
            except (OSError, sqlite3.Error):
                yedek = None
            with app.db.toplu():
                for t in ("ogrenci", "ilerleme", "anlik", "olay", "mesaj", "gunluk") + (("kayit", "esleme") if v.get("liste") else ()):
                    app.db.yap("DELETE FROM " + t)
            app.gunluk("Öğrenci verileri temizlendi (%s)%s" % (k["kullanici"], "; sınıf listesi de silindi" if v.get("liste") else ""))
            return J({"ok": True, "yedek": yedek})
        raise Hata(404, "Bilinmeyen API.")

    def _giris_yap(self, kullanici, parola):
        app = self.app
        k = app.db.tek("SELECT * FROM kullanici WHERE kullanici=?", (str(kullanici or "").strip().lower(),))
        if not k or not parola_dogru(str(parola or ""), k["tuz"], k["ozet"]):
            time.sleep(0.6)      # parola denemelerini yavaşlatır
            raise Hata(403, "Kullanıcı adı ya da parola yanlış.")
        belirtec = secrets.token_urlsafe(32)
        app.db.yap("DELETE FROM oturum WHERE bitis<?", (simdi(),))
        app.db.yap("INSERT INTO oturum (belirtec, kullanici_id, bitis) VALUES (?,?,?)", (belirtec, k["id"], simdi() + OTURUM_SN))
        app.gunluk("Giriş: " + k["kullanici"] + " (" + self.istemci_ip() + ")")
        return self.json_gonder({"ok": True, "kullanici": k["kullanici"], "ad": k["ad"], "rol": k["rol"]},
                                basliklar={"Set-Cookie": "afi_oturum=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax" % (belirtec, OTURUM_SN)})


def portal_html(app, uyglar):
    satir = "".join('<a class="k" href="/%s/"><b>%s</b><span>sürüm %s</span></a>' % (u["uygulama"], u["ad"], u["surum"]) for u in uyglar)
    return ("<!doctype html><html lang='tr'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>%s</title>"
            "<style>body{font-family:Segoe UI,system-ui,sans-serif;background:#EEF2F6;color:#1A2230;margin:0;padding:32px 16px}main{max-width:640px;margin:0 auto}"
            "h1{margin:0 0 16px}.k{display:flex;justify-content:space-between;background:#fff;border:1px solid #D6DDE6;border-radius:14px;padding:16px 18px;margin:10px 0;color:inherit;text-decoration:none}"
            ".k:hover{border-color:#2563C9}span{color:#6F7B8E}</style><main><h1>%s</h1>%s<p><a href='/panel/'>Öğretmen paneli</a></p></main></html>") % (app.ad, app.ad, satir or "<p>Henüz uygulama kurulmadı.</p>")


# ======================================================================= başlatma
def _zaten_calisiyor(port):
    try:
        b = ortak.http_json("http://127.0.0.1:%d/api/v1/bilgi" % port, zaman_asimi=1.5)
        return bool(b and b.get("sistem") == ortak.SISTEM and b.get("rol") == "sunucu")
    except (OSError, ValueError):
        return False


def calistir(argv=None):
    for akim in (sys.stdout, sys.stderr):     # Windows'ta Türkçe harfler yüzünden çökmesin
        try:
            akim.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if sys.stdout is None:                    # penceresiz exe
        sys.stdout = sys.stderr = open(os.devnull, "w")
    kurulum = ortak.kurulum_bilgisi()
    p = argparse.ArgumentParser(description="afi sınıf sunucusu")
    p.add_argument("--port", type=int, default=int(os.environ.get("AFI_PORT") or kurulum.get("port") or ortak.VARSAYILAN_PORT))
    p.add_argument("--veri", default=None, help="kayıt klasörü (varsayılan: kurulumda seçilen ya da programın yanındaki afi-sunucu-veri)")
    p.add_argument("--guncelleme-adresi", default=None)
    p.add_argument("--tarayici-acma", action="store_true", help="başlarken paneli tarayıcıda açma")
    p.add_argument("--konsol", action="store_true", help="bilgileri bu pencerede yazdır (simge yerine)")
    p.add_argument("--deneme", action="store_true", help="başlat, kendini dene ve kapan (kurulum testi)")
    args = p.parse_args(argv)
    if args.veri:
        os.environ["AFI_VERI"] = args.veri
    panel = "http://localhost:%d/panel/" % args.port
    gizli = ortak.donduruldu() and sys.platform == "win32" and not args.konsol and not args.deneme
    if not args.deneme and _zaten_calisiyor(args.port):       # ikinci kez açıldıysa yalnızca paneli aç
        if not args.tarayici_acma:
            webbrowser.open(panel)
        return 0
    veri = ortak.veri_klasoru("sunucu")
    app = Sunucu(veri, port=args.port, guncelleme_adresi=args.guncelleme_adresi)
    if kurulum.get("ad") and kurulum.get("ad") != app.db.ayar("kurulum_adi"):      # kurulumda yazılan ad (yeniden kurulumda değiştiyse)
        app.ad = str(kurulum["ad"]).strip()[:60] or app.ad
        app.db.ayar_yaz("sunucu_adi", app.ad)
        app.db.ayar_yaz("kurulum_adi", kurulum["ad"])
    try:
        httpd = app.baslat()
    except OSError as e:
        mesaj = ("%d numaralı port başka bir program tarafından kullanılıyor ya da açılamadı (%s).\n\n"
                 "Kurulum dosyasını yeniden çalıştırıp başka bir port seçebilirsiniz (ör. 8001).") % (args.port, e)
        app.gunluk("Port açılamadı: %s" % e)
        if gizli:
            ortak.uyari("afi sınıf sunucusu", mesaj)
        else:
            print("\n  " + mesaj + "\n")
            if not args.deneme:
                input("  Kapatmak için Enter'a basın...")
        return 1
    adresler, ad_adresi = app.adresler()
    if not gizli:
        print("=" * 64)
        print("  afi sınıf sunucusu çalışıyor   (platform %s)" % ortak.PLATFORM_SURUM)
        for u in app.paketler.uygulamalar():
            print("  Uygulama: %s %s" % (u["ad"], u["surum"]))
        print("-" * 64)
        print("  Öğrenciler tarayıcıda şu adreslerden birini açar:")
        for a in adresler:
            print("     " + a)
        print("     " + ad_adresi + "   (IP değişse de çalışır)")
        print("  Öğretmen paneli:  " + panel)
        print("  Kayıtlar:         " + veri)
        print("  Kapatmak için bu pencereyi kapatın ya da Ctrl+C.")
        print("=" * 64)
    app.gunluk("Sunucu başladı, port %d (%s)" % (args.port, "simge" if gizli else "pencere"))
    if not args.deneme:
        threading.Thread(target=app._yedek_dongu, daemon=True).start()
    if args.deneme:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        bilgi = ortak.http_json("http://127.0.0.1:%d/api/v1/bilgi" % args.port)
        print("DENEME:", json.dumps(bilgi, ensure_ascii=False))
        httpd.shutdown()
        return 0 if bilgi.get("sistem") == ortak.SISTEM else 2
    if not args.tarayici_acma:
        threading.Timer(1.0, lambda: webbrowser.open(panel)).start()
    app.kapat = httpd.shutdown
    if gizli:
        from . import tepsi
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        if tepsi.calistir(app, panel, httpd):          # görev çubuğundaki afi simgesi; "Sunucuyu kapat" deyince döner
            return 0
        t.join()                                       # simge açılamadıysa yalnızca sunucu çalışır (panelden kapatılabilir)
        return 0
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
