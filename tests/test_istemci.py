"""Öğrenci istemcisi testleri. Çalıştırmak için:  python -m unittest discover tests"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from afi_sinif import istemci, ortak, sunucu  # noqa: E402
from tests.test_sunucu import Istemci as Tarayici, sahte_paket  # noqa: E402

OGR = {"ad": "Deniz", "robot": "pati"}


def sunucu_ac(klasor, surum="9.1"):
    app = sunucu.Sunucu(os.path.join(klasor, "sunucu-veri"), port=0, sessiz=True)
    app.paketler.kur(sahte_paket(klasor, surum))
    httpd = app.baslat()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return app, httpd, "http://127.0.0.1:%d" % httpd.server_address[1]


class IstemciTesti(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.klasor = tempfile.mkdtemp(prefix="afi-istemci-test-")
        cls.ist = istemci.Istemci(os.path.join(cls.klasor, "istemci-veri"), port=0)
        cls.ist.ayar["tarama"] = False
        cls.ihttpd = cls.ist.baslat(arka_plan=False)      # döngüyü testte elle çeviriyoruz
        threading.Thread(target=cls.ihttpd.serve_forever, daemon=True).start()
        cls.t = Tarayici("http://127.0.0.1:%d" % cls.ist.port)
        cls.sunucu = None

    @classmethod
    def tearDownClass(cls):
        cls.ihttpd.shutdown()
        cls.ihttpd.server_close()
        if cls.sunucu:
            cls.sunucu[1].shutdown()
            cls.sunucu[1].server_close()
        shutil.rmtree(cls.klasor, ignore_errors=True)

    def test_01_sunucusuz_calisir(self):
        kod, b = self.t.iste("/api/v1/bilgi")
        self.assertEqual(b["rol"], "istemci")
        self.assertFalse(b["sunucu_bagli"])
        self.assertTrue(b["uygulamalar"], "programla gelen paket kurulmalı")
        kod, html = self.t.iste("/afi-kod/index.html")
        self.assertEqual(kod, 200)
        self.assertIn(b"sinif.js", html)
        kod, c = self.t.iste("/api/v1/nabiz", {"uygulama": "afi-kod", "ogrenci": OGR, "olaylar": [{"tur": "basari", "adim": "a1"}]})
        self.assertTrue(c["cevrimdisi"])
        kod, c = self.t.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": OGR, "veri": {"stars": {"a1": 3}, "ws": {"a1": {"x": 1}}}})
        self.assertEqual(c["veri"]["stars"]["a1"], 3)
        kod, c = self.t.iste("/api/v1/ilerleme?uygulama=afi-kod&ad=DEN%C4%B0Z&robot=pati")
        self.assertEqual(c["veri"]["stars"]["a1"], 3, "ağ yokken de ilerleme bu bilgisayardan gelir")
        self.assertEqual(len(self.ist.kuyruk["kirli"]), 1)
        self.assertEqual(len(self.ist.kuyruk["olaylar"]), 1)
        kod, c = self.t.iste("/api/v1/nabiz", {"uygulama": "afi-kod", "ogrenci": OGR})
        self.assertEqual(len(self.ist.kuyruk["olaylar"]), 1)
        kod, c = self.t.iste("/api/v1/kimlik", {"uygulama": "afi-kod", "eski": OGR, "yeni": {"ad": "Deniz", "robot": "rover"}})
        self.assertTrue(c["cevrimdisi"])
        kod, c = self.t.iste("/api/v1/ilerleme?uygulama=afi-kod&ad=Deniz&robot=rover")
        self.assertEqual(c["veri"]["stars"]["a1"], 3)
        kod, html = self.t.iste("/durum")
        self.assertIn("afi istemci".encode(), html)

    def test_02_sunucuyu_bulur_esitler_gunceller(self):
        app, httpd, adres = sunucu_ac(self.klasor, "9.1")
        type(self).sunucu = (app, httpd, adres)
        self.ist.ayar["sunucu_adlari"] = ["127.0.0.1"]
        self.ist.ayar["portlar"] = [httpd.server_address[1]]
        self.ist.bir_tur()
        self.assertEqual(self.ist.sunucu, adres)
        # bekleyen ilerleme ve kimlik değişikliği sunucuya gitti
        self.assertEqual(self.ist.kuyruk["kirli"], {})
        self.assertEqual(app.ilerleme_oku("afi-kod", "Deniz", "rover")["veri"]["stars"]["a1"], 3)
        # yeni paket indirildi, doğrulandı, etkinleşti
        self.assertEqual(self.ist.paketler.aktif("afi-kod")[0], "9.1")
        kod, c = self.t.iste("/api/v1/nabiz", {"uygulama": "afi-kod", "ogrenci": {"ad": "Deniz", "robot": "rover"}, "adim": {"id": "a2"}})
        self.assertFalse(c.get("cevrimdisi"))
        self.assertEqual(c["surum"], "9.1")
        r = app.db.tek("SELECT * FROM ogrenci WHERE anahtar=?", (ortak.anahtar_yap("Deniz", "rover"),))
        self.assertEqual(r["istemci"], 1)
        self.assertEqual(r["oturum"], ortak.windows_kullanici(), "Windows kullanıcı adı panelde görünür")
        self.assertEqual(r["adim"], "a2")
        self.assertGreaterEqual(app.db.tek("SELECT COUNT(*) AS n FROM olay")["n"], 1, "çevrimdışı olaylar da gitti")
        kod, b = self.t.iste("/api/v1/bilgi")
        self.assertTrue(b["sunucu_bagli"])
        self.assertIn("127.0.0.1", self.ist.ayar["son_adresler"][0])

    def test_03_ogretmen_mesaji_ve_surum_bildirimi(self):
        app = self.sunucu[0]
        app.mesaj_gonder({"rol": "admin", "ad": "Aydın", "araliklar": "[]"}, "*", "Mola!")
        app.mesaj_gonder({"rol": "admin", "ad": "Aydın", "araliklar": "[]"}, "*", "Yeni sürüm 9.2", tur="surum")
        kod, c = self.t.iste("/api/v1/nabiz", {"uygulama": "afi-kod", "ogrenci": {"ad": "Deniz", "robot": "rover"}})
        metinler = [m["metin"] for m in c["mesajlar"]]
        self.assertIn("Mola!", metinler)
        self.assertNotIn("Yeni sürüm 9.2", metinler, "sürüm bildirimi paket bu bilgisayara inince verilir")

    def test_04_sunucu_kapanir_ip_degisir_yeniden_bulur(self):
        app, httpd, adres = self.sunucu
        httpd.shutdown()
        httpd.server_close()
        kod, c = self.t.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": {"ad": "Deniz", "robot": "rover"}, "veri": {"stars": {"b1": 2}}})
        self.assertEqual(kod, 200)
        self.assertFalse(self.ist.bagli())
        self.assertEqual(len(self.ist.kuyruk["kirli"]), 1)
        # öğretmen bilgisayarı yeni adresle (başka port) açıldı; ağ taramasıyla bulunur
        app2 = sunucu.Sunucu(app.veri, port=0, sessiz=True)
        httpd2 = app2.baslat()
        threading.Thread(target=httpd2.serve_forever, daemon=True).start()
        type(self).sunucu = (app2, httpd2, "http://127.0.0.1:%d" % httpd2.server_address[1])
        self.ist.ayar["tarama"] = True
        self.ist.tarama_hedefleri = lambda: [("127.0.0.1", 1), ("127.0.0.1", httpd2.server_address[1])]
        self.ist.bir_tur()
        self.assertTrue(self.ist.bagli())
        self.assertEqual(app2.ilerleme_oku("afi-kod", "Deniz", "rover")["veri"]["stars"]["b1"], 2)
        self.assertEqual(self.ist.kuyruk["kirli"], {})

    def test_05_sunucu_eski_surume_donerse_istemci_de_doner(self):
        app = self.sunucu[0]
        app.paketler.kur(sahte_paket(self.klasor, "9.3"))
        self.ist.bir_tur()
        self.assertEqual(self.ist.paketler.aktif("afi-kod")[0], "9.3")
        app.paketler.sec("afi-kod", "9.1")
        self.ist.bir_tur()
        self.assertEqual(self.ist.paketler.aktif("afi-kod")[0], "9.1")

    def test_06_bozuk_paket_kurulmaz(self):
        app = self.sunucu[0]
        app.paketler.kur(sahte_paket(self.klasor, "9.4"))
        z = app.paketler.zip_yolu("afi-kod", "9.4")
        eski = app.paketler.uygulamalar

        def yanlis():
            u = eski()
            for x in u:
                x["sha256"] = "0" * 64
            return u
        app.paketler.uygulamalar = yanlis
        try:
            self.ist.bir_tur()
        finally:
            app.paketler.uygulamalar = eski
        self.assertTrue(os.path.isfile(z))
        self.assertEqual(self.ist.paketler.aktif("afi-kod")[0], "9.1")
        self.assertIn("başarısız", self.ist.guncelleme_mesaj)

    def test_07_elle_adres(self):
        port = self.sunucu[1].server_address[1]
        kod, c = self.t.iste("/api/v1/ayar", {"sunucu": "127.0.0.1:%d" % port})
        self.assertEqual(c["sunucu"], "http://127.0.0.1:%d" % port)
        self.assertEqual(self.ist.adaylar()[0], "http://127.0.0.1:%d" % port)
        self.ist.bir_tur()
        self.assertTrue(self.ist.bagli())
        kod, c = self.t.iste("/api/v1/durum")
        self.assertEqual(c["ayar"]["sunucu"], "http://127.0.0.1:%d" % port)

    def test_08_ayni_baglantida_okunmamis_govde(self):
        """Gövdesi okunmayan bir POST'tan sonra aynı bağlantıdaki istek bozulmamalı (keep-alive)."""
        import http.client
        b = http.client.HTTPConnection("127.0.0.1", self.ist.port, timeout=5)
        b.request("POST", "/api/v1/ara", body=b'{"x": 1}', headers={"Content-Type": "application/json"})
        r = b.getresponse()
        r.read()
        self.assertEqual(r.status, 200)
        b.request("POST", "/api/v1/nabiz", body=json.dumps({"uygulama": "afi-kod", "ogrenci": OGR}).encode(), headers={"Content-Type": "application/json"})
        r = b.getresponse()
        self.assertEqual(r.status, 200, r.read()[:80])
        b.close()


if __name__ == "__main__":
    unittest.main()
