"""Sunucu testleri. Çalıştırmak için (isikcirobot_offline klasöründe):  python -m unittest discover tests"""
import http.cookiejar
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from afi_sinif import ortak, sunucu  # noqa: E402


def sahte_paket(klasor, surum, uyg="afi-kod"):
    yol = os.path.join(klasor, "%s-%s.zip" % (uyg, surum))
    with zipfile.ZipFile(yol, "w") as z:
        z.writestr("afi-paket.json", json.dumps({"uygulama": uyg, "ad": "AFİ KOD", "surum": surum, "giris": "index.html"}))
        z.writestr("index.html", "<!doctype html><title>AFİ KOD %s</title>" % surum)
        z.writestr("js/version.js", "window.AFI_VERSION = '%s';" % surum)
    return yol


class Istemci:
    """Çerezleri tutan küçük HTTP istemcisi (tarayıcı gibi)."""

    def __init__(self, taban):
        self.taban = taban
        self.acici = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def iste(self, yol, veri=None, yontem=None, ham=None, tur="application/json"):
        govde = ham if ham is not None else (None if veri is None else json.dumps(veri).encode())
        r = urllib.request.Request(self.taban + yol, data=govde, method=yontem or ("POST" if govde is not None else "GET"), headers={"Content-Type": tur})
        try:
            with self.acici.open(r, timeout=10) as c:
                icerik = c.read()
                return c.status, (json.loads(icerik) if c.headers.get("Content-Type", "").startswith("application/json") else icerik)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")


class SunucuTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.klasor = tempfile.mkdtemp(prefix="afi-test-")
        cls.app = sunucu.Sunucu(os.path.join(cls.klasor, "veri"), port=0, sessiz=True)
        cls.app.paketler.kur(sahte_paket(cls.klasor, "2.1"))
        cls.httpd = cls.app.baslat()
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.taban = "http://127.0.0.1:%d" % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.klasor, ignore_errors=True)

    def test_01_bilgi_ve_kurulum(self):
        i = Istemci(self.taban)
        kod, b = i.iste("/api/v1/bilgi")
        self.assertEqual(kod, 200)
        self.assertEqual(b["sistem"], "afi-sinif")
        self.assertTrue(b["kurulum_gerekli"])
        kod, b = i.iste("/api/v1/sinif")
        self.assertEqual(kod, 401)
        kod, b = i.iste("/api/v1/kurulum", {"kullanici": "aydin", "ad": "Aydın", "sifre": "kisa"})
        self.assertEqual(kod, 400)
        kod, b = i.iste("/api/v1/kurulum", {"kullanici": "aydin", "ad": "Aydın İncekara", "sifre": "gizli123"})
        self.assertEqual(kod, 200, b)
        self.assertEqual(b["rol"], "admin")
        kod, b = i.iste("/api/v1/kurulum", {"kullanici": "ikinci", "ad": "x", "sifre": "gizli123"})
        self.assertEqual(kod, 403)
        kod, b = i.iste("/api/v1/ben")
        self.assertTrue(b["giris"])

    def test_02_ogretmen_ve_araliklar(self):
        admin = Istemci(self.taban)
        self.assertEqual(admin.iste("/api/v1/giris", {"kullanici": "aydin", "sifre": "gizli123"})[0], 200)
        kod, b = admin.iste("/api/v1/kullanicilar", {"kullanici": "ayse", "ad": "Ayşe Öğretmen", "sifre": "parola99", "araliklar": ["192.168.1.0/24"]})
        self.assertEqual(kod, 200, b)
        kod, b = admin.iste("/api/v1/kullanicilar", {"kullanici": "x", "sifre": "parola99", "araliklar": ["192.168.1.999/24"]})
        self.assertEqual(kod, 400)
        self.assertEqual(Istemci(self.taban).iste("/api/v1/giris", {"kullanici": "ayse", "sifre": "yanlis"})[0], 403)
        # iki farklı ağdan öğrenci
        self.app.nabiz({"uygulama": "afi-kod", "ogrenci": {"ad": "Ali", "robot": "pati"}, "adim": {"id": "salon-3", "ad": "Salon 3"}, "durum": "calisiyor", "yildiz": 7, "biten": 3}, "192.168.1.20")
        self.app.nabiz({"uygulama": "afi-kod", "ogrenci": {"ad": "Zeynep", "robot": "afi"}, "yildiz": 2, "biten": 1}, "192.168.2.30")
        ogr = Istemci(self.taban)
        self.assertEqual(ogr.iste("/api/v1/giris", {"kullanici": "ayse", "sifre": "parola99"})[0], 200)
        kod, b = ogr.iste("/api/v1/sinif")
        adlar = [o["ad"] for o in b["ogrenciler"]]
        self.assertEqual(adlar, ["Ali"])
        self.assertTrue(b["ogrenciler"][0]["cevrimici"])
        kod, b = admin.iste("/api/v1/sinif")
        self.assertEqual(sorted(o["ad"] for o in b["ogrenciler"]), ["Ali", "Zeynep"])
        # öğretmen admin işi yapamaz
        self.assertEqual(ogr.iste("/api/v1/kullanicilar")[0], 403)

    def test_03_ilerleme_birlestirme_ve_anlik(self):
        i = Istemci(self.taban)
        o = {"ad": "Deniz", "robot": "rover"}
        i.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {"salon-1": 3, "salon-2": 1}, "ws": {"salon-1": {"a": 1}}, "last": "salon-2"}})
        kod, b = i.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": {"ad": " deniz ", "robot": "rover"}, "veri": {"stars": {"salon-1": 2, "salon-2": 3, "salon-3": 1}}})
        self.assertEqual(b["veri"]["stars"], {"salon-1": 3, "salon-2": 3, "salon-3": 1})
        self.assertEqual(b["veri"]["last"], "salon-2")
        kod, b = i.iste("/api/v1/ilerleme?uygulama=afi-kod&ad=DENIZ&robot=rover")
        self.assertEqual(b["veri"]["stars"]["salon-2"], 3)
        kod, b = i.iste("/api/v1/ilerleme?uygulama=afi-kod&ad=Deniz&robot=afi")
        self.assertIsNone(b["veri"])       # başka robot = başka öğrenci
        self.assertEqual(i.iste("/api/v1/anlik", {"uygulama": "afi-kod", "ogrenci": o, "adim": "salon-3", "ws": {"blocks": {}}, "kod": "ileri_git()"})[0], 200)

    def test_035_kimlik_tasima(self):
        i = Istemci(self.taban)
        i.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": {"ad": "Can", "robot": "afi"}, "veri": {"stars": {"salon-1": 3}}})
        self.app.nabiz({"uygulama": "afi-kod", "ogrenci": {"ad": "Can", "robot": "afi"}}, "192.168.1.50")
        self.assertEqual(i.iste("/api/v1/kimlik", {"uygulama": "afi-kod", "eski": {"ad": "Can", "robot": "afi"}, "yeni": {"ad": "Can", "robot": "zipzip"}})[0], 200)
        self.assertIsNone(i.iste("/api/v1/ilerleme?uygulama=afi-kod&ad=Can&robot=afi")[1]["veri"])
        self.assertEqual(i.iste("/api/v1/ilerleme?uygulama=afi-kod&ad=Can&robot=zipzip")[1]["veri"]["stars"], {"salon-1": 3})
        self.assertEqual(self.app.db.tek("SELECT robot FROM ogrenci WHERE anahtar=?", (ortak.anahtar_yap("Can", "zipzip"),))["robot"], "zipzip")

    def test_04_mesajlar(self):
        admin = Istemci(self.taban)
        admin.iste("/api/v1/giris", {"kullanici": "aydin", "sifre": "gizli123"})
        ogr = {"uygulama": "afi-kod", "ogrenci": {"ad": "Ece", "robot": "bocuk"}}
        self.assertEqual(self.app.nabiz(ogr, "192.168.1.40")["mesajlar"], [])
        admin.iste("/api/v1/mesaj", {"hedef": "*", "metin": "Herkes Bölüm 2'ye geçsin"})
        admin.iste("/api/v1/mesaj", {"hedef": ortak.anahtar_yap("Ece", "bocuk"), "metin": "Ece, harika gidiyorsun!"})
        m = self.app.nabiz(ogr, "192.168.1.40")["mesajlar"]
        self.assertEqual([x["metin"] for x in m], ["Herkes Bölüm 2'ye geçsin", "Ece, harika gidiyorsun!"])
        self.assertEqual(self.app.nabiz(ogr, "192.168.1.40")["mesajlar"], [])     # bir kez teslim edilir
        # aralıklı öğretmenin "herkese" mesajı başka ağa gitmez
        ayse = Istemci(self.taban)
        ayse.iste("/api/v1/giris", {"kullanici": "ayse", "sifre": "parola99"})
        ayse.iste("/api/v1/mesaj", {"hedef": "*", "metin": "1. sınıfa mesaj"})
        z = self.app.nabiz({"uygulama": "afi-kod", "ogrenci": {"ad": "Zeynep", "robot": "afi"}}, "192.168.2.30")["mesajlar"]
        self.assertEqual([x["metin"] for x in z], ["Herkes Bölüm 2'ye geçsin"])     # admin'in mesajı gelir, Ayşe'ninki gelmez
        self.assertEqual(len(self.app.nabiz(ogr, "192.168.1.40")["mesajlar"]), 1)

    def test_05_statik_ve_paket(self):
        i = Istemci(self.taban)
        kod, icerik = i.iste("/afi-kod/index.html")
        self.assertIn(b"AFI", icerik.upper().replace("İ".encode(), b"I"))
        self.assertIn(i.iste("/afi-kod/../../veri/afi-sinif.db")[0], (403, 404))
        kod, b = i.iste("/api/v1/paket")
        self.assertEqual(b["afi-kod"]["surum"], "2.1")
        kod, z = i.iste("/api/v1/paket/afi-kod.zip")
        self.assertEqual(kod, 200)
        import hashlib
        self.assertEqual(hashlib.sha256(z).hexdigest(), b["afi-kod"]["sha256"])
        kod, panel = i.iste("/panel/")
        self.assertEqual(kod, 200)

    def test_06_guncelleme_zinciri(self):
        """Sahte bir 'GitHub' sunucusu: version.json + paket. Denetle, kur, geri dön."""
        site = os.path.join(self.klasor, "site")
        os.makedirs(os.path.join(site, "paketler"))
        z = sahte_paket(os.path.join(site, "paketler"), "2.3")
        vj = {"uygulamalar": {"afi-kod": {"ad": "AFİ KOD", "surum": "2.3", "zip": "paketler/afi-kod-2.3.zip", "sha256": ortak.sha256_dosya(z)}}}
        with open(os.path.join(site, "version.json"), "w") as f:
            json.dump(vj, f)

        class Sessiz(SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                SimpleHTTPRequestHandler.__init__(self, *a, directory=site, **k)

            def log_message(self, *a):
                pass
        gh = ThreadingHTTPServer(("127.0.0.1", 0), Sessiz)
        threading.Thread(target=gh.serve_forever, daemon=True).start()
        try:
            os.environ["no_proxy"] = os.environ["NO_PROXY"] = "127.0.0.1,localhost"
            admin = Istemci(self.taban)
            admin.iste("/api/v1/giris", {"kullanici": "aydin", "sifre": "gizli123"})
            admin.iste("/api/v1/ayarlar", {"guncelleme_adresi": "http://127.0.0.1:%d/version.json" % gh.server_address[1]})
            kod, b = admin.iste("/api/v1/guncelleme/denetle", {})
            self.assertEqual(kod, 200, b)
            self.assertTrue(b["uygulamalar"][0]["yeni"])
            kod, b = admin.iste("/api/v1/guncelleme/kur", {"uygulama": "afi-kod"})
            self.assertEqual(kod, 200, b)
            self.assertEqual(self.app.paketler.aktif("afi-kod")[0], "2.3")
            # istemciye "yeni sürüm" bildirimi gider
            m = self.app.nabiz({"uygulama": "afi-kod", "ogrenci": {"ad": "Ece", "robot": "bocuk"}}, "192.168.1.40")["mesajlar"]
            self.assertTrue(any(x["tur"] == "surum" for x in m))
            # bozuk paket reddedilir
            with open(z, "ab") as f:
                f.write(b"bozuk")
            vj["uygulamalar"]["afi-kod"]["surum"] = "2.4"
            with open(os.path.join(site, "version.json"), "w") as f:
                json.dump(vj, f)
            kod, b = admin.iste("/api/v1/guncelleme/kur", {"uygulama": "afi-kod"})
            self.assertEqual(kod, 400)
            self.assertIn("doğrulama", b["hata"])
            # önceki sürüme dönüş
            self.assertEqual(admin.iste("/api/v1/guncelleme/sec", {"uygulama": "afi-kod", "surum": "2.1"})[0], 200)
            self.assertEqual(self.app.paketler.aktif("afi-kod")[0], "2.1")
            # elle (USB'den) yükleme
            ham = open(sahte_paket(self.klasor, "2.5"), "rb").read()
            kod, b = admin.iste("/api/v1/guncelleme/yukle", ham=ham, tur="application/zip")
            self.assertEqual(kod, 200, b)
            self.assertEqual(self.app.paketler.aktif("afi-kod")[0], "2.5")
        finally:
            gh.shutdown()
            gh.server_close()

    def test_07_csv_yedek_temizle(self):
        admin = Istemci(self.taban)
        admin.iste("/api/v1/giris", {"kullanici": "aydin", "sifre": "gizli123"})
        kod, csvv = admin.iste("/api/v1/disa-aktar.csv")
        self.assertIn("Ali".encode(), csvv)
        kod, db = admin.iste("/api/v1/yedek")
        self.assertTrue(db.startswith(b"SQLite format 3"))
        self.assertEqual(admin.iste("/api/v1/temizle", {"onay": "evet"})[0], 400)

    def test_08_guvensiz_zip(self):
        yol = os.path.join(self.klasor, "kotu.zip")
        with zipfile.ZipFile(yol, "w") as z:
            z.writestr("afi-paket.json", json.dumps({"uygulama": "afi-kod", "surum": "9.9"}))
            z.writestr("../../kotu.txt", "x")
        with self.assertRaises(ortak.PaketHatasi):
            self.app.paketler.kur(yol)

    def test_09_aralik(self):
        self.assertTrue(ortak.aralikta("192.168.137.45", ["192.168.137.0/24"]))
        self.assertTrue(ortak.aralikta("10.0.0.15", ["10.0.0.10-10.0.0.20"]))
        self.assertFalse(ortak.aralikta("10.0.0.25", ["10.0.0.10-10.0.0.20"]))
        self.assertEqual(ortak.anahtar_yap("  IŞIL  Yılmaz", "pati"), ortak.anahtar_yap("ışıl yilmaz", "pati"))


if __name__ == "__main__":
    unittest.main()
