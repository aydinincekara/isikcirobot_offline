"""afi sınıf öğrenci istemcisi - öğrenci bilgisayarında çalışır.

Neden var?  Ağ kesilse de, öğretmen bilgisayarı kapalı olsa da öğrenci çalışmaya devam edebilsin.
- AFİ KOD'u bu bilgisayardan sunar: http://127.0.0.1:8100  (yalnızca bu bilgisayar erişir; güvenlik duvarı izni gerekmez)
- Öğretmen sunucusunu kendisi bulur: son bilinen adres -> bilgisayar adı -> yerel ağda tarama. IP değişse de bulur.
- Sunucu varken: ilerlemeyi, canlı durumu ve olayları sunucuya iletir, öğretmen mesajlarını getirir.
- Sunucu yokken: her şeyi bu bilgisayarda saklar, bağlantı gelince gönderir.
- Sunucuda yeni bir uygulama sürümü varsa indirir, doğrular ve kurar ("Yeni sürüm hazır" bildirimi çıkar).
"""
import argparse
import concurrent.futures
import hashlib
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from http.server import ThreadingHTTPServer

from . import ortak
from .ortak import Hata, simdi
from .sunucu import ilerleme_birlestir

ARA_SN = 20             # bağlı değilken bu aralıkla sunucu aranır
DENETIM_SN = 30         # bağlıyken bu aralıkla bağlantı ve güncelleme denetlenir


class Istemci:
    def __init__(self, veri_klasoru, port=ortak.ISTEMCI_PORT):
        self.veri = veri_klasoru
        os.makedirs(veri_klasoru, exist_ok=True)
        self.port = port
        self.ayar_yolu = os.path.join(veri_klasoru, "ayarlar.json")
        self.ayar = ortak.json_oku(self.ayar_yolu, {}) or {}
        self.paketler = ortak.PaketDeposu(os.path.join(veri_klasoru, "paketler"))
        self.ilerleme_klasor = os.path.join(veri_klasoru, "ilerleme")
        os.makedirs(self.ilerleme_klasor, exist_ok=True)
        self.kuyruk_yolu = os.path.join(veri_klasoru, "kuyruk.json")
        self.kuyruk = ortak.json_oku(self.kuyruk_yolu, {}) or {}       # {"olaylar": [...], "kirli": {anahtar: kimlik}, "kimlik": [...]}
        for k, v in (("olaylar", []), ("kirli", {}), ("kimlik", []), ("anlik", {})):
            self.kuyruk.setdefault(k, v)
        self.kilit = threading.RLock()
        self.sunucu = None          # "http://192.168.1.20:8000"
        self.sunucu_bilgi = None
        self.son_temas = 0
        self.durum_mesaj = "Sunucu aranıyor..."
        self.guncelleme_mesaj = ""
        self.lan_ip = (ortak.yerel_ipler() or ["127.0.0.1"])[0]
        self.uyandir = threading.Event()
        for k in self.paketler.gomulu_paketleri_kur():
            self.gunluk("Program içindeki paket kuruldu: " + k)

    # ------------------------------------------------------------ yardımcılar
    def gunluk(self, satir):
        try:
            yol = os.path.join(self.veri, "gunluk.txt")
            with open(yol, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + satir + "\n")
            if os.path.getsize(yol) > 2 * 1024 * 1024:
                os.replace(yol, yol + ".eski")
        except OSError:
            pass

    def ayar_kaydet(self):
        ortak.json_yaz(self.ayar_yolu, self.ayar)

    def kuyruk_kaydet(self):
        with self.kilit:
            ortak.json_yaz(self.kuyruk_yolu, self.kuyruk)

    def _il_yolu(self, uyg, anahtar):
        return os.path.join(self.ilerleme_klasor, uyg + "-" + hashlib.sha1(anahtar.encode("utf-8")).hexdigest()[:16] + ".json")

    def yerel_ilerleme(self, uyg, anahtar):
        return (ortak.json_oku(self._il_yolu(uyg, anahtar), {}) or {}).get("veri") or {}

    def yerel_ilerleme_yaz(self, uyg, anahtar, kimlik, veri):
        ortak.json_yaz(self._il_yolu(uyg, anahtar), {"anahtar": anahtar, "kimlik": kimlik, "uygulama": uyg, "veri": veri, "zaman": simdi()})

    def bagli(self):
        return bool(self.sunucu)

    def kopar(self, neden=""):
        if self.sunucu:
            self.gunluk("Sunucu bağlantısı koptu: " + self.sunucu + " " + neden)
        self.sunucu = None
        self.durum_mesaj = "Sunucuya ulaşılamıyor; çalışmalar bu bilgisayarda saklanıyor."
        self.uyandir.set()

    def gonder(self, yol, veri=None, zaman=4.0):
        """Sunucuya istek; bağlantı hatasında bağlantıyı koparır ve OSError fırlatır."""
        if not self.sunucu:
            raise OSError("bağlı değil")
        try:
            return ortak.http_json(self.sunucu + "/api/v1/" + yol, veri, zaman_asimi=zaman)
        except OSError as e:
            if getattr(e, "code", None) and 400 <= e.code < 500:
                raise
            self.kopar(str(e))
            raise

    # ------------------------------------------------------------ sunucu bulma
    def _dene(self, adres, zaman=1.5):
        try:
            b = ortak.http_json(adres + "/api/v1/bilgi", zaman_asimi=zaman)
            if b and b.get("sistem") == ortak.SISTEM and b.get("rol") == "sunucu":
                return b
        except (OSError, ValueError):
            pass
        return None

    def adaylar(self):
        """Önce elle girilen adres, sonra son bilinen adres ve bilgisayar adı, en son ağ taraması."""
        a = []
        for x in [self.ayar.get("sunucu")] + list(self.ayar.get("son_adresler") or []):
            if x and x not in a:
                a.append(x.rstrip("/"))
        portlar = self.ayar.get("portlar") or [ortak.VARSAYILAN_PORT]
        for ad in self.ayar.get("sunucu_adlari") or []:
            for p in portlar:
                u = "http://%s:%d" % (ad, p)
                if u not in a:
                    a.append(u)
        return a

    def tarama_hedefleri(self):
        portlar = self.ayar.get("portlar") or [ortak.VARSAYILAN_PORT]
        hedefler = []
        for ip in ortak.yerel_ipler():
            try:
                ag = ipaddress.ip_network(ip + "/24", strict=False)
            except ValueError:
                continue
            if ag.is_loopback:
                continue
            for h in ag.hosts():
                for p in portlar:
                    hedefler.append((str(h), p))
        if "192.168.137.1" not in [h for h, _ in hedefler]:
            hedefler.insert(0, ("192.168.137.1", ortak.VARSAYILAN_PORT))     # Windows mobil etkin nokta
        return hedefler

    def tara(self):
        """Yerel ağdaki /24 bloklarını tarar (yalnızca dışarı bağlantı kurar; güvenlik duvarı sormaz)."""
        hedefler = self.tarama_hedefleri()

        def acik(hp):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.35)
            try:
                return hp if s.connect_ex(hp) == 0 else None
            except OSError:
                return None
            finally:
                s.close()
        bulunan = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
            for r in ex.map(acik, hedefler):
                if r:
                    bulunan.append(r)
        for h, p in bulunan:
            adres = "http://%s:%d" % (h, p)
            b = self._dene(adres)
            if b:
                return adres, b
        return None, None

    def bul(self):
        for adres in self.adaylar():
            b = self._dene(adres)
            if b:
                return adres, b
        if self.ayar.get("tarama", True):
            return self.tara()
        return None, None

    def baglan(self, adres, bilgi):
        ilk = self.sunucu != adres
        self.sunucu, self.sunucu_bilgi, self.son_temas = adres, bilgi, simdi()
        self.durum_mesaj = "Sunucuya bağlı: " + (bilgi.get("ad") or adres)
        son = [adres] + [x for x in (self.ayar.get("son_adresler") or []) if x != adres]
        self.ayar["son_adresler"] = son[:5]
        if bilgi.get("bilgisayar"):
            adlar = [bilgi["bilgisayar"]] + [x for x in (self.ayar.get("sunucu_adlari") or []) if x != bilgi["bilgisayar"]]
            self.ayar["sunucu_adlari"] = adlar[:3]
            if bilgi.get("port") and bilgi["port"] not in (self.ayar.get("portlar") or [ortak.VARSAYILAN_PORT]):
                self.ayar["portlar"] = [ortak.VARSAYILAN_PORT, bilgi["port"]]
        self.ayar_kaydet()
        if ilk:
            self.gunluk("Sunucuya bağlandı: " + adres)

    # ------------------------------------------------------------ eşitleme ve güncelleme
    def esitle(self):
        """Bağlantı yokken biriken her şeyi gönderir."""
        with self.kilit:
            kimlikler, self.kuyruk["kimlik"] = self.kuyruk["kimlik"], []
            kirli = dict(self.kuyruk["kirli"])
            anlik = dict(self.kuyruk["anlik"])
        for anahtar, b in kirli.items():
            try:
                c = self.gonder("ilerleme", {"uygulama": b["uygulama"], "ogrenci": b["kimlik"], "veri": self.yerel_ilerleme(b["uygulama"], anahtar)}, zaman=10)
                self.yerel_ilerleme_yaz(b["uygulama"], anahtar, b["kimlik"], ilerleme_birlestir(self.yerel_ilerleme(b["uygulama"], anahtar), c.get("veri")))
                with self.kilit:
                    self.kuyruk["kirli"].pop(anahtar, None)
            except OSError:
                break
        for k in kimlikler:                  # önce eski kimlikle ilerleme gider, sonra sunucuda yeni kimliğe taşınır
            try:
                self.gonder("kimlik", k)
            except OSError:
                with self.kilit:
                    self.kuyruk["kimlik"].append(k)
        for anahtar, v in anlik.items():
            try:
                self.gonder("anlik", v)
                with self.kilit:
                    self.kuyruk["anlik"].pop(anahtar, None)
            except OSError:
                break
        self.kuyruk_kaydet()

    def guncelle(self):
        try:
            uzak = self.gonder("paket", zaman=5)
        except (OSError, ValueError):
            return
        for uyg, b in (uzak or {}).items():
            s = str(b.get("surum") or "")
            if not s or s == self.paketler.aktif(uyg)[0]:
                continue
            if s in self.paketler.surumler(uyg):          # sunucu eski sürüme döndüyse ya da daha önce indirildiyse
                self.paketler.sec(uyg, s)
                self.guncelleme_mesaj = "%s %s etkinleştirildi." % (uyg, s)
                self.gunluk(self.guncelleme_mesaj)
                continue
            self.guncelleme_mesaj = "%s %s indiriliyor..." % (uyg, b.get("surum"))
            gecici = tempfile.mkdtemp(prefix="indir-", dir=self.veri)
            try:
                yol = os.path.join(gecici, "paket.zip")
                ortak.http_indir(self.sunucu + "/api/v1/paket/" + urllib.parse.quote(uyg) + ".zip", yol, zaman_asimi=120, yerel=True)
                m = self.paketler.kur(yol, beklenen_sha=b.get("sha256"))
                self.paketler.temizle(uyg, sakla=2)
                self.guncelleme_mesaj = "%s %s kuruldu." % (uyg, m["surum"])
                self.gunluk("Güncellendi: %s %s" % (uyg, m["surum"]))
            except (OSError, ValueError, ortak.PaketHatasi) as e:
                self.guncelleme_mesaj = "Güncelleme başarısız: " + str(e)
                self.gunluk(self.guncelleme_mesaj)
            finally:
                shutil.rmtree(gecici, ignore_errors=True)

    def bir_tur(self):
        if not self.sunucu:
            adres, b = self.bul()
            if adres:
                self.baglan(adres, b)
        if self.sunucu:
            b = self._dene(self.sunucu, 3)
            if not b:
                self.kopar("yanıt yok")
            else:
                self.baglan(self.sunucu, b)
                self.esitle()
                self.guncelle()

    def dongu(self):
        while True:
            try:
                self.bir_tur()
            except Exception as e:       # arka plan hiçbir zaman durmasın
                self.gunluk("Döngü hatası: " + repr(e))
            self.uyandir.wait(DENETIM_SN if self.sunucu else ARA_SN)
            self.uyandir.clear()

    # ------------------------------------------------------------ uygulamanın istekleri
    def nabiz(self, v):
        v = dict(v)
        cihaz = dict(v.get("cihaz") or {})
        cihaz.update({"istemci": True, "ad": ortak.bilgisayar_adi(), "ip": self.lan_ip})
        v["cihaz"] = cihaz
        with self.kilit:
            eski_olaylar = self.kuyruk["olaylar"]
            self.kuyruk["olaylar"] = []
        v["olaylar"] = (eski_olaylar + list(v.get("olaylar") or []))[-60:]
        try:
            c = self.gonder("nabiz", v)
            sunucudaki = c.get("surum")
            c["surum"] = self.paketler.aktif(v.get("uygulama") or "afi-kod")[0]   # uygulama, bu bilgisayardaki sürüme göre bildirim gösterir
            c["mesajlar"] = [m for m in (c.get("mesajlar") or []) if m.get("tur") != "surum"]   # paket inince bildirim "surum" alanından gelir
            if sunucudaki and sunucudaki != c["surum"]:
                self.uyandir.set()          # arka plan hemen indirsin
            if self.kuyruk["kirli"] or self.kuyruk["kimlik"] or self.kuyruk["anlik"]:
                threading.Thread(target=self.esitle, daemon=True).start()
            return c
        except OSError:
            with self.kilit:
                self.kuyruk["olaylar"] = (v["olaylar"] + self.kuyruk["olaylar"])[-200:]
            self.kuyruk_kaydet()
            return {"ok": True, "cevrimdisi": True, "mesajlar": [], "surum": self.paketler.aktif(v.get("uygulama") or "afi-kod")[0]}

    def ilerleme_yaz(self, v):
        uyg = str(v.get("uygulama") or "afi-kod")
        k = v.get("ogrenci") or {}
        anahtar = ortak.anahtar_yap(k.get("ad"), k.get("robot"))
        birlesik = ilerleme_birlestir(self.yerel_ilerleme(uyg, anahtar), v.get("veri") or {})
        self.yerel_ilerleme_yaz(uyg, anahtar, k, birlesik)
        try:
            c = self.gonder("ilerleme", {"uygulama": uyg, "ogrenci": k, "veri": v.get("veri") or {}}, zaman=6)
            birlesik = ilerleme_birlestir(birlesik, c.get("veri"))
            self.yerel_ilerleme_yaz(uyg, anahtar, k, birlesik)
        except OSError:
            with self.kilit:
                self.kuyruk["kirli"][anahtar] = {"uygulama": uyg, "kimlik": k}
            self.kuyruk_kaydet()
        return {"ok": True, "veri": birlesik}

    def ilerleme_oku(self, uyg, ad, robot):
        anahtar = ortak.anahtar_yap(ad, robot)
        yerel = self.yerel_ilerleme(uyg, anahtar)
        try:
            c = self.gonder("ilerleme?" + urllib.parse.urlencode({"uygulama": uyg, "ad": ad, "robot": robot}), zaman=5)
            if c.get("veri"):
                yerel = ilerleme_birlestir(yerel, c["veri"])
                self.yerel_ilerleme_yaz(uyg, anahtar, {"ad": ad, "robot": robot}, yerel)
        except OSError:
            pass
        return {"veri": yerel or None}

    def anlik(self, v):
        try:
            return self.gonder("anlik", v)
        except OSError:
            k = v.get("ogrenci") or {}
            with self.kilit:
                self.kuyruk["anlik"][ortak.anahtar_yap(k.get("ad"), k.get("robot"))] = v
            return {"ok": True, "cevrimdisi": True}

    def kimlik(self, v):
        uyg = str(v.get("uygulama") or "afi-kod")
        e, y = v.get("eski") or {}, v.get("yeni") or {}
        ea, ya = ortak.anahtar_yap(e.get("ad"), e.get("robot")), ortak.anahtar_yap(y.get("ad"), y.get("robot"))
        eski = self.yerel_ilerleme(uyg, ea)
        if eski:
            self.yerel_ilerleme_yaz(uyg, ya, y, ilerleme_birlestir(self.yerel_ilerleme(uyg, ya), eski))
        try:
            return self.gonder("kimlik", v)
        except OSError:
            with self.kilit:
                self.kuyruk["kimlik"].append(v)
                if eski:
                    self.kuyruk["kirli"][ya] = {"uygulama": uyg, "kimlik": y}
            self.kuyruk_kaydet()
            return {"ok": True, "cevrimdisi": True}

    def bilgi(self):
        return {"sistem": ortak.SISTEM, "rol": "istemci", "ad": "afi istemci", "platform": ortak.PLATFORM_SURUM,
                "uygulamalar": [{k: u[k] for k in ("uygulama", "ad", "surum")} for u in self.paketler.uygulamalar()],
                "sunucu_bagli": self.bagli(), "sunucu": self.sunucu, "sunucu_ad": (self.sunucu_bilgi or {}).get("ad"),
                "cihaz": ortak.bilgisayar_adi(), "ip": self.lan_ip}

    # ------------------------------------------------------------ çalıştırma
    def baslat(self, arka_plan=True):
        istemci = self

        class Isleyici(IstemciIsleyici):
            pass
        Isleyici.app = istemci
        httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Isleyici)
        httpd.daemon_threads = True
        self.port = httpd.server_address[1]
        self.httpd = httpd
        if arka_plan:
            threading.Thread(target=self.dongu, daemon=True).start()
        return httpd


class IstemciIsleyici(ortak.TemelIsleyici):
    app = None

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self._yonet("GET")

    def do_POST(self):
        self._yonet("POST")

    def _yonet(self, yontem):
        try:
            if not self.yerelden_mi():
                raise Hata(403, "Yalnızca bu bilgisayardan erişilebilir.")
            parca = urllib.parse.urlsplit(self.path)
            yol, q = parca.path, dict(urllib.parse.parse_qsl(parca.query))
            app = self.app
            if yol.startswith("/api/v1/"):
                a = yol[len("/api/v1/"):]
                if a == "bilgi":
                    return self.json_gonder(app.bilgi())
                if a == "nabiz" and yontem == "POST":
                    return self.json_gonder(app.nabiz(self.json_govde()))
                if a == "ilerleme" and yontem == "POST":
                    return self.json_gonder(app.ilerleme_yaz(self.json_govde()))
                if a == "ilerleme":
                    return self.json_gonder(app.ilerleme_oku(q.get("uygulama", "afi-kod"), q.get("ad", ""), q.get("robot", "afi")))
                if a == "anlik" and yontem == "POST":
                    return self.json_gonder(app.anlik(self.json_govde()))
                if a == "kimlik" and yontem == "POST":
                    return self.json_gonder(app.kimlik(self.json_govde()))
                if a == "ben":
                    return self.json_gonder({"giris": False, "ogretmen": False})
                if a == "durum":
                    return self.json_gonder(dict(app.bilgi(), mesaj=app.durum_mesaj, guncelleme=app.guncelleme_mesaj, adaylar=app.adaylar(),
                                                 bekleyen=len(app.kuyruk["kirli"]) + len(app.kuyruk["olaylar"]), ayar={k: app.ayar.get(k) for k in ("sunucu", "tarama")}))
                if a == "ayar" and yontem == "POST":
                    v = self.json_govde()
                    adr = str(v.get("sunucu") or "").strip().rstrip("/")
                    if adr and not adr.startswith("http"):
                        adr = "http://" + adr
                    if adr and ":" not in adr.split("//", 1)[1]:
                        adr += ":%d" % ortak.VARSAYILAN_PORT
                    app.ayar["sunucu"] = adr or None
                    if "tarama" in v:
                        app.ayar["tarama"] = bool(v["tarama"])
                    app.ayar_kaydet()
                    app.kopar("ayar değişti")
                    return self.json_gonder({"ok": True, "sunucu": app.ayar["sunucu"]})
                if a == "kapat" and yontem == "POST":        # yeni sürüm kurulurken eski kopya kapanır
                    self.json_gonder({"ok": True})
                    threading.Thread(target=app.httpd.shutdown, daemon=True).start()
                    return
                if a == "ara" and yontem == "POST":
                    app.kopar("elle arama")
                    return self.json_gonder({"ok": True})
                raise Hata(404, "Bilinmeyen API.")
            if yontem != "GET":
                raise Hata(405, "Yöntem desteklenmiyor.")
            if yol in ("/", ""):
                uyglar = app.paketler.uygulamalar()
                return self.yonlendir("/" + (uyglar[0]["uygulama"] if uyglar else "durum") + "/")
            if yol.rstrip("/") == "/durum":
                return self.gonder(200, DURUM_HTML, "text/html; charset=utf-8")
            if yol.startswith("/panel"):
                if app.sunucu:
                    return self.yonlendir(app.sunucu + yol)
                raise Hata(503, "Öğretmen sunucusuna ulaşılamıyor.")
            parcalar = yol.lstrip("/").split("/", 1)
            s, klasor = app.paketler.aktif(parcalar[0])
            if not klasor:
                raise Hata(404, "Bulunamadı.")
            if len(parcalar) == 1:
                return self.yonlendir("/" + parcalar[0] + "/")
            return self.dosya_gonder(klasor, parcalar[1])
        except Hata as h:
            self.hata_gonder(h.kod, h.mesaj)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.app.gunluk("HATA " + self.path + " " + repr(e))
            self.hata_gonder(500, str(e))


DURUM_HTML = """<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>afi istemci</title>
<style>:root{color-scheme:light dark}body{font-family:Segoe UI,system-ui,sans-serif;margin:0;padding:24px 16px;background:Canvas;color:CanvasText}main{max-width:620px;margin:0 auto}
.k{border:1px solid #8884;border-radius:14px;padding:16px;margin:12px 0}b.ok{color:#1F8A5B}b.no{color:#C2413B}input{padding:8px;border-radius:8px;border:1px solid #8886;width:100%;box-sizing:border-box;font:inherit}
button{padding:8px 14px;border-radius:8px;border:1px solid #8886;font:inherit;font-weight:700;cursor:pointer;margin-top:8px}small{opacity:.7}a{color:#2563C9}</style>
<main><h1>afi istemci</h1><div class="k" id="d">Yükleniyor...</div>
<div class="k"><b>Sunucu adresi</b><p><small>Boş bırakılırsa sunucu ağda kendiliğinden aranır. Örnek: 192.168.1.20:8000 ya da OGRETMEN-PC:8000</small></p>
<input id="s" placeholder="otomatik bul"><button id="k">Kaydet ve bağlan</button> <button id="a">Şimdi ara</button></div>
<p><a href="/">AFİ KOD'a dön</a></p></main>
<script>
function y(){fetch('/api/v1/durum').then(r=>r.json()).then(d=>{document.getElementById('d').innerHTML=
'<p>Durum: '+(d.sunucu_bagli?'<b class=ok>Sunucuya bağlı</b> ('+(d.sunucu_ad||'')+' · '+d.sunucu+')':'<b class=no>Bağlı değil</b> — çalışmalar bu bilgisayarda saklanıyor')+'</p>'+
'<p><small>'+d.mesaj+(d.guncelleme?'<br>'+d.guncelleme:'')+'</small></p><p>Bu bilgisayar: '+d.cihaz+' ('+d.ip+') · bekleyen kayıt: '+d.bekleyen+'</p>'+
'<p>Uygulamalar: '+d.uygulamalar.map(u=>u.ad+' '+u.surum).join(', ')+' · platform '+d.platform+'</p>';
var s=document.getElementById('s');if(document.activeElement!==s)s.value=d.ayar.sunucu||'';})}
document.getElementById('k').onclick=()=>fetch('/api/v1/ayar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sunucu:document.getElementById('s').value})}).then(()=>setTimeout(y,1500));
document.getElementById('a').onclick=()=>fetch('/api/v1/ara',{method:'POST'}).then(()=>setTimeout(y,3000));
y();setInterval(y,3000);
</script></html>"""


# ======================================================================= Windows kurulumu
def kurulu_yol():
    taban = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(taban, "afi-sinif", "afi-istemci.exe")


def kisayol_olustur(exe):
    """Masaüstüne 'AFİ KOD' ve Başlangıç klasörüne arka planda çalışan kısayol (yönetici izni gerekmez)."""
    ps = (
        "$s=New-Object -ComObject WScript.Shell;"
        "$d=[Environment]::GetFolderPath('Desktop');$b=[Environment]::GetFolderPath('Startup');"
        "$l=$s.CreateShortcut((Join-Path $d 'AFİ KOD.lnk'));$l.TargetPath='%s';$l.WorkingDirectory='%s';$l.Description='AFİ KOD';$l.Save();"
        "$k=$s.CreateShortcut((Join-Path $b 'afi istemci.lnk'));$k.TargetPath='%s';$k.Arguments='--arka-plan';$k.WorkingDirectory='%s';$k.Save()"
    ) % (exe, os.path.dirname(exe), exe, os.path.dirname(exe))
    kod = __import__("base64").b64encode(ps.encode("utf-16-le")).decode()
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", kod],
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=60)


def kur():
    """USB'den çift tıklanan exe kendini %LOCALAPPDATA%\\afi-sinif klasörüne kopyalar, kısayolları açar ve başlar."""
    hedef = kurulu_yol()
    kaynak = os.path.abspath(sys.executable)
    if os.path.normcase(kaynak) != os.path.normcase(hedef):
        os.makedirs(os.path.dirname(hedef), exist_ok=True)
        try:                                   # eski sürüm çalışıyorsa kapat ki üzerine yazılabilsin
            ortak.http_json("http://127.0.0.1:%d/api/v1/kapat" % ortak.ISTEMCI_PORT, {}, zaman_asimi=2)
        except (OSError, ValueError):
            pass
        for _ in range(10):
            try:
                shutil.copyfile(kaynak, hedef)
                break
            except OSError:
                time.sleep(0.7)
    try:
        kisayol_olustur(hedef)
    except (OSError, subprocess.SubprocessError):
        pass
    return hedef


# ======================================================================= başlatma
def calistir(argv=None):
    for akim in (sys.stdout, sys.stderr):     # Windows'ta Türkçe harfler yüzünden çökmesin
        try:
            akim.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if sys.stdout is None:                    # pencere olmadan (--noconsole) çalışırken print hata vermesin
        sys.stdout = sys.stderr = open(os.devnull, "w")
    p = argparse.ArgumentParser(description="afi sınıf öğrenci istemcisi")
    p.add_argument("--port", type=int, default=int(os.environ.get("AFI_ISTEMCI_PORT") or ortak.ISTEMCI_PORT))
    p.add_argument("--veri", default=None)
    p.add_argument("--sunucu", default=None, help="sunucu adresi (örnek 192.168.1.20:8000); verilmezse kendisi bulur")
    p.add_argument("--arka-plan", action="store_true", help="tarayıcı açmadan çalış (Windows açılışında)")
    p.add_argument("--kur", action="store_true", help="bu bilgisayara kur ve kısayolları oluştur")
    p.add_argument("--kurma", action="store_true", help="kurulum yapmadan çalış")
    p.add_argument("--deneme", action="store_true", help="başlat, kendini dene ve kapan")
    args = p.parse_args(argv)
    if args.veri:
        os.environ["AFI_VERI"] = args.veri
    if ortak.donduruldu() and sys.platform == "win32" and not args.kurma and not args.deneme:
        hedef = kurulu_yol()
        if args.kur or os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(hedef):
            yeni = kur()
            if os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(yeni) and os.path.isfile(yeni):
                subprocess.Popen([yeni], close_fds=True)
                return 0
    adres = "http://127.0.0.1:%d/" % args.port
    try:                                      # zaten çalışıyorsa sadece tarayıcıyı aç
        b = ortak.http_json(adres + "api/v1/bilgi", zaman_asimi=1.0)
        if b and b.get("rol") == "istemci":
            if not args.arka_plan:
                webbrowser.open(adres)
            return 0
    except (OSError, ValueError):
        pass
    app = Istemci(ortak.veri_klasoru("istemci"), port=args.port)
    if args.sunucu:
        adr = args.sunucu if args.sunucu.startswith("http") else "http://" + args.sunucu
        app.ayar["sunucu"] = adr.rstrip("/")
        app.ayar_kaydet()
    try:
        httpd = app.baslat()
    except OSError as e:
        app.gunluk("Port açılamadı: %s" % e)
        return 1
    app.gunluk("İstemci başladı: " + adres)
    if args.deneme:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        b = ortak.http_json(adres + "api/v1/bilgi")
        print("DENEME:", json.dumps(b, ensure_ascii=False))
        httpd.shutdown()
        return 0 if b.get("rol") == "istemci" and b.get("uygulamalar") else 2
    if not args.arka_plan:
        threading.Timer(0.8, lambda: webbrowser.open(adres)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
