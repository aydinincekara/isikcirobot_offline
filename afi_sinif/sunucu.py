"""afi sınıf sunucusu - öğretmen bilgisayarında çalışır.

- AFİ KOD'u (ve ileride başka ders uygulamalarını) yerel ağa sunar: öğrenciler http://ogretmen-pc:8000 adresini açar.
- Öğrencilerin ilerlemesini ve canlı durumunu toplar; öğretmen panelinde gösterir (/panel).
- Admin ve öğretmen hesapları; her öğretmen yalnızca kendi ağ aralığındaki öğrencileri görür.
- Öğrenci istemcilerine (afi-istemci) güncel uygulama paketini dağıtır.
- GitHub'daki isikcirobot_offline sayfasından yeni sürümü denetler, indirir, doğrular ve kurar; önceki sürüme dönülebilir.
"""
import argparse
import base64
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

CEVRIMICI_SN = 30
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
    return ""          # son nabızdan bu kadar saniye geçmediyse öğrenci "çevrimiçi"
OTURUM_SN = 12 * 3600


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
"""


class Veritabani:
    def __init__(self, yol):
        self.yol = yol
        self.kilit = threading.RLock()
        self.b = sqlite3.connect(yol, check_same_thread=False)
        self.b.row_factory = sqlite3.Row
        with self.kilit:
            self.b.executescript(SEMA)
            self.b.execute("PRAGMA journal_mode=WAL")
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
            self.b.commit()
            return c.lastrowid

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
    """Yıldızlarda büyük olan kalır; bloklarda yeni gelen kazanır; görülen hikâyeler birleşir."""
    eski = dict(eski or {})
    yeni = yeni or {}
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
    if yeni.get("last"):
        eski["last"] = yeni["last"]
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
        self.guncelleme_durum = {"calisiyor": False, "mesaj": ""}
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

    # ------------------------------------------------------------ öğrenci tarafı
    def nabiz(self, v, ip):
        uyg = str(v.get("uygulama") or "afi-kod")[:40]
        ogr = v.get("ogrenci") or {}
        ad = str(ogr.get("ad") or "").strip()[:40]
        if not ad:
            raise Hata(400, "Öğrenci adı yok.")
        robot = str(ogr.get("robot") or "afi")[:20]
        anahtar = ortak.anahtar_yap(ad, robot)
        cihaz = v.get("cihaz") or {}
        adim = v.get("adim") or {}
        ip = str(cihaz.get("ip") or ip) if cihaz.get("istemci") and ip.startswith("127.") else ip
        simd = simdi()
        mevcut = self.db.tek("SELECT son_mesaj FROM ogrenci WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
        if mevcut is None:
            son_id = (self.db.tek("SELECT MAX(id) AS m FROM mesaj")["m"] or 0)
            self.db.yap("INSERT INTO ogrenci (anahtar, uygulama, ad, robot, ilk, son, son_mesaj) VALUES (?,?,?,?,?,?,?)", (anahtar, uyg, ad, robot, simd, simd, son_id))
            son_mesaj = son_id
            self.gunluk("Yeni öğrenci: " + ad + " (" + ip + ")")
        else:
            son_mesaj = mevcut["son_mesaj"] or 0
        self.db.yap("UPDATE ogrenci SET ad=?, robot=?, ip=?, cihaz=?, istemci=?, son=?, adim=?, adim_ad=?, durum=?, yildiz=?, biten=? WHERE anahtar=? AND uygulama=?",
                    (ad, robot, ip, str(cihaz.get("ad") or ip_adi(ip) or "")[:60], 1 if cihaz.get("istemci") else 0, simd, str(adim.get("id") or "")[:40],
                     str(adim.get("ad") or "")[:120], str(v.get("durum") or "")[:20], int(v.get("yildiz") or 0), int(v.get("biten") or 0), anahtar, uyg))
        for o in (v.get("olaylar") or [])[:20]:
            self.db.yap("INSERT INTO olay (zaman, anahtar, uygulama, tur, adim, ayrinti) VALUES (?,?,?,?,?,?)",
                        (float(o.get("zaman") or simd), anahtar, uyg, str(o.get("tur") or "")[:20], str(o.get("adim") or "")[:40], json.dumps(o.get("ayrinti"), ensure_ascii=False)[:500]))
        mesajlar = []
        for m in self.db.sorgu("SELECT * FROM mesaj WHERE id>? AND (hedef=? OR hedef='*') ORDER BY id", (son_mesaj, anahtar)):
            araliklar = json.loads(m["araliklar"] or "[]")
            if m["hedef"] == "*" and araliklar and not ortak.aralikta(ip, araliklar):
                continue
            mesajlar.append({"id": m["id"], "metin": m["metin"], "tur": m["tur"], "gonderen": m["gonderen"], "zaman": m["zaman"]})
        en_son = self.db.tek("SELECT MAX(id) AS m FROM mesaj")["m"] or 0
        if en_son > son_mesaj:
            self.db.yap("UPDATE ogrenci SET son_mesaj=? WHERE anahtar=? AND uygulama=?", (en_son, anahtar, uyg))
        surum = self.paketler.aktif(uyg)[0]
        return {"ok": True, "mesajlar": mesajlar, "surum": surum, "anahtar": anahtar}

    def ilerleme_yaz(self, v):
        uyg = str(v.get("uygulama") or "afi-kod")[:40]
        ogr = v.get("ogrenci") or {}
        anahtar = ortak.anahtar_yap(ogr.get("ad"), ogr.get("robot"))
        if anahtar.startswith("|"):
            raise Hata(400, "Öğrenci adı yok.")
        r = self.db.tek("SELECT veri FROM ilerleme WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
        birlesik = ilerleme_birlestir(json.loads(r["veri"]) if r else {}, v.get("veri") or {})
        self.db.yap("INSERT OR REPLACE INTO ilerleme (anahtar, uygulama, veri, guncelleme) VALUES (?,?,?,?)", (anahtar, uyg, json.dumps(birlesik, ensure_ascii=False), simdi()))
        return {"ok": True, "veri": birlesik}

    def ilerleme_oku(self, uyg, ad, robot):
        r = self.db.tek("SELECT veri, guncelleme FROM ilerleme WHERE anahtar=? AND uygulama=?", (ortak.anahtar_yap(ad, robot), uyg))
        return {"veri": json.loads(r["veri"]) if r else None, "guncelleme": r["guncelleme"] if r else None}

    def kimlik_tasi(self, v):
        """Öğrenci robotunu (ya da adını) değiştirince kayıtları yeni kimliğe taşır."""
        uyg = str(v.get("uygulama") or "afi-kod")[:40]
        e, y = v.get("eski") or {}, v.get("yeni") or {}
        eski, yeni = ortak.anahtar_yap(e.get("ad"), e.get("robot")), ortak.anahtar_yap(y.get("ad"), y.get("robot"))
        if eski == yeni or eski.startswith("|") or yeni.startswith("|"):
            return {"ok": True}
        with self.db.kilit:
            ie = self.db.tek("SELECT veri FROM ilerleme WHERE anahtar=? AND uygulama=?", (eski, uyg))
            iy = self.db.tek("SELECT veri FROM ilerleme WHERE anahtar=? AND uygulama=?", (yeni, uyg))
            if ie:
                birlesik = ilerleme_birlestir(json.loads(iy["veri"]) if iy else {}, json.loads(ie["veri"]))
                self.db.yap("INSERT OR REPLACE INTO ilerleme (anahtar, uygulama, veri, guncelleme) VALUES (?,?,?,?)", (yeni, uyg, json.dumps(birlesik, ensure_ascii=False), simdi()))
                self.db.yap("DELETE FROM ilerleme WHERE anahtar=? AND uygulama=?", (eski, uyg))
            for tablo in ("ogrenci", "anlik"):
                if self.db.tek("SELECT 1 AS v FROM " + tablo + " WHERE anahtar=? AND uygulama=?", (yeni, uyg)):
                    self.db.yap("DELETE FROM " + tablo + " WHERE anahtar=? AND uygulama=?", (eski, uyg))
                else:
                    self.db.yap("UPDATE " + tablo + " SET anahtar=? WHERE anahtar=? AND uygulama=?", (yeni, eski, uyg))
            self.db.yap("UPDATE ogrenci SET robot=? WHERE anahtar=? AND uygulama=?", (str(y.get("robot") or "afi")[:20], yeni, uyg))
            self.db.yap("UPDATE olay SET anahtar=? WHERE anahtar=? AND uygulama=?", (yeni, eski, uyg))
        return {"ok": True}

    def anlik_yaz(self, v):
        uyg = str(v.get("uygulama") or "afi-kod")[:40]
        ogr = v.get("ogrenci") or {}
        anahtar = ortak.anahtar_yap(ogr.get("ad"), ogr.get("robot"))
        ws = v.get("ws")
        self.db.yap("INSERT OR REPLACE INTO anlik (anahtar, uygulama, adim, ws, kod, guncelleme) VALUES (?,?,?,?,?,?)",
                    (anahtar, uyg, str(v.get("adim") or "")[:40], json.dumps(ws, ensure_ascii=False)[:400000] if ws is not None else None, str(v.get("kod") or "")[:20000], simdi()))
        return {"ok": True}

    # ------------------------------------------------------------ öğretmen tarafı
    def sinif(self, kullanici, uyg=None):
        simd = simdi()
        satirlar = self.db.sorgu("SELECT * FROM ogrenci" + (" WHERE uygulama=?" if uyg else "") + " ORDER BY ad", (uyg,) if uyg else ())
        out = []
        for r in satirlar:
            if not self.gorebilir(kullanici, r["ip"] or ""):
                continue
            r.pop("son_mesaj", None)
            r["cevrimici"] = bool(r["son"] and simd - r["son"] < CEVRIMICI_SN)
            out.append(r)
        return out

    def ogrenci_ayrinti(self, kullanici, uyg, anahtar):
        r = self.db.tek("SELECT * FROM ogrenci WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
        if not r or not self.gorebilir(kullanici, r["ip"] or ""):
            raise Hata(404, "Öğrenci bulunamadı.")
        il = self.db.tek("SELECT veri FROM ilerleme WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
        an = self.db.tek("SELECT adim, ws, kod, guncelleme FROM anlik WHERE anahtar=? AND uygulama=?", (anahtar, uyg))
        olaylar = self.db.sorgu("SELECT zaman, tur, adim, ayrinti FROM olay WHERE anahtar=? AND uygulama=? ORDER BY id DESC LIMIT 60", (anahtar, uyg))
        veri = json.loads(il["veri"]) if il else {}
        r.pop("son_mesaj", None)
        r["cevrimici"] = bool(r["son"] and simdi() - r["son"] < CEVRIMICI_SN)
        return {"ogrenci": r, "yildizlar": veri.get("stars") or {}, "anlik": {"adim": an["adim"], "ws": json.loads(an["ws"]) if an and an["ws"] else None,
                "kod": an["kod"] if an else "", "guncelleme": an["guncelleme"] if an else None} if an else None, "olaylar": olaylar}

    def mesaj_gonder(self, kullanici, hedef, metin, tur="mesaj"):
        metin = str(metin or "").strip()[:500]
        if not metin and tur == "mesaj":
            raise Hata(400, "Mesaj boş.")
        araliklar = json.loads(kullanici.get("araliklar") or "[]") if kullanici["rol"] != "admin" else []
        mid = self.db.yap("INSERT INTO mesaj (hedef, araliklar, metin, tur, gonderen, zaman) VALUES (?,?,?,?,?,?)",
                          (hedef or "*", json.dumps(araliklar), metin, tur, kullanici["ad"], simdi()))
        return {"ok": True, "id": mid}

    def csv_uret(self, kullanici, uyg):
        cikti = io.StringIO()
        y = csv.writer(cikti, delimiter=";")
        y.writerow(["Ad", "Robot", "Bilgisayar", "IP", "Biten adım", "Toplam yıldız", "Şu anki adım", "İlk görülme", "Son görülme"])
        for r in self.sinif(kullanici, uyg):
            y.writerow([r["ad"], r["robot"], r["cihaz"], r["ip"], r["biten"], r["yildiz"], r["adim_ad"] or r["adim"],
                        time.strftime("%d.%m.%Y %H:%M", time.localtime(r["ilk"] or 0)), time.strftime("%d.%m.%Y %H:%M", time.localtime(r["son"] or 0))])
        return "﻿" + cikti.getvalue()      # BOM: Excel Türkçe karakterleri doğru açsın

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
                      "kurulum_gerekli": app.kullanici_sayisi() == 0, "ip": ip})
        if a == "nabiz" and yontem == "POST":
            return J(app.nabiz(self.json_govde(), ip))
        if a == "ilerleme" and yontem == "POST":
            return J(app.ilerleme_yaz(self.json_govde()))
        if a == "ilerleme" and yontem == "GET":
            return J(app.ilerleme_oku(q.get("uygulama", "afi-kod"), q.get("ad", ""), q.get("robot", "afi")))
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
            return J({"ogrenciler": app.sinif(k, q.get("uygulama")), "simdi": simdi(), "uygulamalar": app.paketler.uygulamalar()})
        if a == "ogrenci":
            return J(app.ogrenci_ayrinti(k, q.get("uygulama", "afi-kod"), q.get("anahtar", "")))
        if a == "mesaj" and yontem == "POST":
            v = self.json_govde()
            return J(app.mesaj_gonder(k, v.get("hedef") or "*", v.get("metin"), "mesaj"))
        if a == "disa-aktar.csv":
            veri = app.csv_uret(k, q.get("uygulama"))
            return self.gonder(200, veri, "text/csv; charset=utf-8", {"Content-Disposition": "attachment; filename=\"afi-sinif-%s.csv\"" % time.strftime("%Y%m%d")})
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
            for t in ("ogrenci", "ilerleme", "anlik", "olay", "mesaj"):
                app.db.yap("DELETE FROM " + t)
            app.gunluk("Öğrenci verileri temizlendi (" + k["kullanici"] + ")")
            return J({"ok": True})
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
def calistir(argv=None):
    for akim in (sys.stdout, sys.stderr):     # Windows'ta Türkçe harfler yüzünden çökmesin
        try:
            akim.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="afi sınıf sunucusu")
    p.add_argument("--port", type=int, default=int(os.environ.get("AFI_PORT") or ortak.VARSAYILAN_PORT))
    p.add_argument("--veri", default=None, help="veri klasörü (varsayılan: programın yanındaki afi-sunucu-veri)")
    p.add_argument("--guncelleme-adresi", default=None)
    p.add_argument("--tarayici-acma", action="store_true", help="başlarken paneli tarayıcıda açma")
    p.add_argument("--deneme", action="store_true", help="başlat, kendini dene ve kapan (kurulum testi)")
    args = p.parse_args(argv)
    if args.veri:
        os.environ["AFI_VERI"] = args.veri
    veri = ortak.veri_klasoru("sunucu")
    app = Sunucu(veri, port=args.port, guncelleme_adresi=args.guncelleme_adresi)
    try:
        httpd = app.baslat()
    except OSError as e:
        print("\n  Port %d kullanımda ya da açılamadı: %s" % (args.port, e))
        print("  Sunucu zaten açık olabilir. Başka port için: afi-sunucu.exe --port 8001\n")
        if not args.deneme:
            input("  Kapatmak için Enter'a basın...")
        return 1
    adresler, ad_adresi = app.adresler()
    print("=" * 64)
    print("  afi sınıf sunucusu çalışıyor   (platform %s)" % ortak.PLATFORM_SURUM)
    for u in app.paketler.uygulamalar():
        print("  Uygulama: %s %s" % (u["ad"], u["surum"]))
    print("-" * 64)
    print("  Öğrenciler tarayıcıda şu adreslerden birini açar:")
    for a in adresler:
        print("     " + a)
    print("     " + ad_adresi + "   (IP değişse de çalışır)")
    print("  Öğretmen paneli:  http://localhost:%d/panel/" % args.port)
    print("  Veriler:          " + veri)
    print("  Kapatmak için bu pencereyi kapatın ya da Ctrl+C.")
    print("=" * 64)
    app.gunluk("Sunucu başladı, port %d" % args.port)
    if args.deneme:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        bilgi = ortak.http_json("http://127.0.0.1:%d/api/v1/bilgi" % args.port)
        print("DENEME:", json.dumps(bilgi, ensure_ascii=False))
        httpd.shutdown()
        return 0 if bilgi.get("sistem") == ortak.SISTEM else 2
    if not args.tarayici_acma:
        threading.Timer(1.0, lambda: webbrowser.open("http://localhost:%d/panel/" % args.port)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
