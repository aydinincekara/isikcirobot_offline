"""Sınıf listesi, öğrenci numarası ve geri bildirim testleri (afi sınıf 1.3).
Çalıştırmak için (isikcirobot_offline klasöründe):  python -m unittest discover tests"""
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from afi_sinif import istemci, ortak, sunucu  # noqa: E402
from tests.test_sunucu import Istemci, sahte_paket  # noqa: E402


def nabiz(ad, robot="afi", pid="p1", kayit=None, adim="salon-1", olaylar=None, **ek):
    ogr = {"ad": ad, "robot": robot, "pid": pid}
    if kayit:
        ogr["kayit"] = kayit
    v = {"uygulama": "afi-kod", "ogrenci": ogr, "adim": {"id": adim, "ad": "Bölüm 1 · " + adim}, "durum": "hazir", "yildiz": 0, "biten": 0, "olaylar": olaylar or []}
    v.update(ek)
    return v


class NumaraTesti(unittest.TestCase):
    def setUp(self):
        self.klasor = tempfile.mkdtemp(prefix="afi-test-")
        self.app = sunucu.Sunucu(os.path.join(self.klasor, "veri"), port=0, sessiz=True)
        self.app.paketler.kur(sahte_paket(self.klasor, "2.5"))
        self.httpd = self.app.baslat()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.taban = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        self.ogretmen = Istemci(self.taban)
        self.ogrenci = Istemci(self.taban)
        self.assertEqual(self.ogretmen.iste("/api/v1/kurulum", {"kullanici": "aydin", "ad": "Aydın", "sifre": "gizli123"})[0], 200)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.app.db.b.close()
        shutil.rmtree(self.klasor, ignore_errors=True)

    def ekle(self, ad, sinif="Cumartesi", **ek):
        kod, c = self.ogretmen.iste("/api/v1/kayitlar", dict({"ad": ad, "sinif": sinif}, **ek))
        self.assertEqual(kod, 200, c)
        return c["kimlik"]

    def sinif(self):
        return {o["ad"]: o for o in self.ogretmen.iste("/api/v1/sinif?uygulama=afi-kod")[1]["ogrenciler"]}

    # ------------------------------------------------------------ liste
    def test_01_ogrenci_ekleme_ve_numara(self):
        a = self.ekle("Elif Yılmaz")
        self.assertRegex(a["no"], r"^\d{4}$")
        b = self.ekle("Can Demir", no="27")
        self.assertEqual(b["no"], "27")
        kod, c = self.ogretmen.iste("/api/v1/kayitlar", {"ad": "Başka", "no": "27"})
        self.assertEqual(kod, 409)
        self.assertIn("Can Demir", c["hata"])
        self.assertEqual(self.ogretmen.iste("/api/v1/kayitlar", {"ad": "  "})[0], 400)
        self.assertEqual(self.ogretmen.iste("/api/v1/kayitlar", {"ad": "X", "no": "abc"})[0], 400)
        # giriş yapmamış biri listeyi göremez, ekleyemez
        self.assertEqual(self.ogrenci.iste("/api/v1/kayitlar")[0], 401)
        self.assertEqual(self.ogrenci.iste("/api/v1/kayitlar", {"ad": "Sızan"})[0], 401)
        # hiç bağlanmamış öğrenci de sınıf ekranında görünür (kaybolmaz)
        s = self.sinif()
        self.assertEqual(set(s), {"Elif Yılmaz", "Can Demir"})
        self.assertFalse(s["Elif Yılmaz"]["cevrimici"])
        self.assertEqual(s["Elif Yılmaz"]["sinif"], "Cumartesi")

    def test_02_toplu_ekleme(self):
        kod, c = self.ogretmen.iste("/api/v1/kayitlar/toplu", {"sinif": "Pazar sabah", "metin": "Ayşe Kaya\n\n  Mehmet  Öz \n105;Zeynep Ak\nDeniz Su\t212\n105;Tekrar Numara\n"})
        self.assertEqual(kod, 200)
        self.assertEqual([e["ad"] for e in c["eklenen"]], ["Ayşe Kaya", "Mehmet Öz", "Zeynep Ak", "Deniz Su"])
        self.assertEqual(c["eklenen"][2]["no"], "105")
        self.assertEqual(c["eklenen"][3]["no"], "212")
        self.assertEqual(len(c["hatalar"]), 1)
        self.assertEqual(len({e["no"] for e in c["eklenen"]}), 4)
        self.assertEqual(self.ogretmen.iste("/api/v1/sinif")[1]["siniflar"], ["Pazar sabah"])
        kod, liste = self.ogretmen.iste("/api/v1/liste.csv")
        self.assertIn("105;Zeynep Ak;Pazar sabah", liste.decode("utf-8-sig"))

    # ------------------------------------------------------------ numarayla giriş: her bilgisayardan aynı öğrenci
    def test_03_numarayla_giris_baska_bilgisayardan_devam(self):
        elif_ = self.ekle("Elif Yılmaz")
        kod, c = self.ogrenci.iste("/api/v1/ogrenci-giris", {"no": elif_["no"]})
        self.assertEqual((kod, c["kimlik"]["ad"], c["kimlik"]["kayit"]), (200, "Elif Yılmaz", elif_["kayit"]))
        self.assertEqual(self.ogrenci.iste("/api/v1/ogrenci-giris", {"no": "0000"})[0], 404)
        # 1. bilgisayar: iki adım bitirir
        o1 = {"ad": "Elif Yılmaz", "robot": "pati", "pid": "pc1-profil", "kayit": elif_["kayit"]}
        self.ogrenci.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o1, "veri": {"stars": {"salon-1": 3, "salon-2": 2}, "ws": {"salon-2": {"b": 1}}, "last": "salon-3"}})
        kod, c = self.ogrenci.iste("/api/v1/nabiz", nabiz("Elif Yılmaz", "pati", "pc1-profil", elif_["kayit"], yildiz=5, biten=2))
        self.assertEqual(c["anahtar"], "#%d" % elif_["kayit"])
        self.assertEqual(c["kimlik"]["robot"], "pati")           # seçtiği robot sunucuda saklanır
        # 2. bilgisayar: yalnızca numarayı bilir; adı farklı yazılmış, robot seçilmemiş olsa bile aynı kayıt
        kod, c = self.ogrenci.iste("/api/v1/ogrenci-giris", {"no": elif_["no"]})
        self.assertEqual(c["kimlik"]["robot"], "pati")
        kod, c = self.ogrenci.iste("/api/v1/ilerleme?uygulama=afi-kod&ad=elif&robot=afi&pid=pc2-profil&kayit=%d" % elif_["kayit"])
        self.assertEqual(c["veri"]["stars"], {"salon-1": 3, "salon-2": 2})
        self.assertEqual(c["veri"]["last"], "salon-3")
        s = self.sinif()
        self.assertEqual(len(s), 1)                               # tek kişi: ikinci bir "Elif" oluşmadı
        self.assertEqual((s["Elif Yılmaz"]["yildiz"], s["Elif Yılmaz"]["biten"], s["Elif Yılmaz"]["no"]), (5, 2, elif_["no"]))

    def test_04_ad_ve_numara_duzenleme(self):
        k = self.ekle("Elif Yilmaz")
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Elif Yilmaz", kayit=k["kayit"]))
        kod, c = self.ogretmen.iste("/api/v1/kayitlar", {"id": k["kayit"], "ad": "Elif Yılmaz", "sinif": "Pazar", "no": "4242", "notu": "gözlüklü"})
        self.assertEqual((kod, c["kimlik"]["no"], c["kimlik"]["ad"]), (200, "4242", "Elif Yılmaz"))
        # öğrencinin tarayıcısı hâlâ eski adı gönderir: sunucudaki ad geçerlidir ve öğrenciye bildirilir
        kod, c = self.ogrenci.iste("/api/v1/nabiz", nabiz("Elif Yilmaz", kayit=k["kayit"]))
        self.assertEqual((c["kimlik"]["ad"], c["kimlik"]["no"], c["kimlik"]["sinif"]), ("Elif Yılmaz", "4242", "Pazar"))
        s = self.sinif()
        self.assertEqual(list(s), ["Elif Yılmaz"])
        self.assertEqual(s["Elif Yılmaz"]["notu"], "gözlüklü")
        self.assertEqual(self.ogrenci.iste("/api/v1/ogrenci-giris", {"no": k["no"]})[0], 404)      # eski numara artık geçmez
        self.assertEqual(self.ogrenci.iste("/api/v1/ogrenci-giris", {"no": "4242"})[0], 200)

    # ------------------------------------------------------------ numarasız öğrenci -> numara
    def test_05_numarasiz_ogrenciye_numara_verme(self):
        o = {"ad": "Ali", "robot": "rover", "pid": "pc7"}
        self.ogrenci.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {"salon-1": 3}}})
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Ali", "rover", "pc7", yildiz=3, biten=1, olaylar=[{"tur": "basari", "adim": "salon-1", "ayrinti": {"yildiz": 3}}]))
        s = self.sinif()
        self.assertEqual((s["Ali"]["kayit"], s["Ali"]["no"]), (None, ""))
        kod, c = self.ogretmen.iste("/api/v1/kayitlar/numara-ver", {"anahtar": s["Ali"]["anahtar"], "sinif": "Cumartesi"})
        self.assertEqual(kod, 200, c)
        kimlik = c["verilen"][0]
        # aynı tarayıcı (pid aynı) eski kimliğiyle nabız atar: numarası kendisine bildirilir, kayıt ikiye bölünmez
        kod, c = self.ogrenci.iste("/api/v1/nabiz", nabiz("Ali", "rover", "pc7"))
        self.assertEqual(c["kimlik"]["no"], kimlik["no"])
        s = self.sinif()
        self.assertEqual(len(s), 1)
        self.assertEqual((s["Ali"]["yildiz"], s["Ali"]["biten"], s["Ali"]["sinif"]), (3, 1, "Cumartesi"))
        d = self.ogretmen.iste("/api/v1/ogrenci?uygulama=afi-kod&anahtar=%23" + str(kimlik["kayit"]))[1]
        self.assertEqual(d["yildizlar"], {"salon-1": 3})
        self.assertEqual(d["adimlar"]["salon-1"]["basari"], 1)
        # başka bilgisayardaki başka bir "Ali" (pid farklı) bu kayda karışmaz
        kod, c = self.ogrenci.iste("/api/v1/nabiz", nabiz("Ali", "rover", "pc9"))
        self.assertIsNone(c["kimlik"])
        self.assertEqual(len(self.ogretmen.iste("/api/v1/sinif")[1]["ogrenciler"]), 2)

    def test_06_herkese_numara_ve_birlestirme(self):
        for i, ad in enumerate(["Ece", "Mert"]):
            self.ogrenci.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": {"ad": ad, "robot": "afi", "pid": "p%d" % i}, "veri": {"stars": {"salon-%d" % (i + 1): 2}}})
            self.ogrenci.iste("/api/v1/nabiz", nabiz(ad, pid="p%d" % i))
        kod, c = self.ogretmen.iste("/api/v1/kayitlar/numara-ver", {"anahtar": "*"})
        self.assertEqual(len(c["verilen"]), 2)
        self.assertTrue(all(o["kayit"] for o in self.sinif().values()))
        # "ece" yanlışlıkla ikinci kez "Ecee" diye girmiş: iki kayıt birleştirilir, yıldızlar toplanır
        self.ogrenci.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": {"ad": "Ecee", "robot": "afi", "pid": "p5"}, "veri": {"stars": {"salon-1": 1, "salon-4": 3}}})
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Ecee", pid="p5"))
        s = self.sinif()
        kod, c = self.ogretmen.iste("/api/v1/kayitlar/birlestir", {"kaynak": s["Ecee"]["anahtar"], "hedef": s["Ece"]["kayit"]})
        self.assertEqual(kod, 200, c)
        s = self.sinif()
        self.assertEqual(set(s), {"Ece", "Mert"})
        d = self.ogretmen.iste("/api/v1/ogrenci?uygulama=afi-kod&anahtar=%23" + str(s["Ece"]["kayit"]))[1]
        self.assertEqual(d["yildizlar"], {"salon-1": 2, "salon-4": 3})
        self.assertEqual((s["Ece"]["yildiz"], s["Ece"]["biten"]), (5, 2))
        # listedeki iki kayıt da birleştirilebilir; kaynak kayıt listeden kalkar
        kod, c = self.ogretmen.iste("/api/v1/kayitlar/birlestir", {"kaynak": "#%d" % s["Mert"]["kayit"], "hedef": s["Ece"]["kayit"]})
        self.assertEqual(kod, 200, c)
        self.assertEqual(set(self.sinif()), {"Ece"})
        self.assertEqual(self.ogretmen.iste("/api/v1/kayitlar/birlestir", {"kaynak": "#%d" % s["Ece"]["kayit"], "hedef": s["Ece"]["kayit"]})[0], 400)

    def test_07_silme(self):
        k = self.ekle("Silinecek")
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Silinecek", kayit=k["kayit"]))
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Numarasız", pid="x"))
        s = self.sinif()
        self.assertEqual(self.ogretmen.iste("/api/v1/kayitlar?id=%d" % k["kayit"], yontem="DELETE")[0], 200)
        self.assertEqual(self.ogretmen.iste("/api/v1/ogrenci?uygulama=afi-kod&anahtar=" + s["Numarasız"]["anahtar"].replace("|", "%7C"), yontem="DELETE")[0], 200)
        self.assertEqual(self.sinif(), {})
        self.assertEqual(self.ogrenci.iste("/api/v1/ogrenci-giris", {"no": k["no"]})[0], 404)

    # ------------------------------------------------------------ sıfırlama
    def test_08_ilerleme_sifirlama_geri_dolmaz(self):
        k = self.ekle("Reset")
        o = {"ad": "Reset", "robot": "afi", "pid": "p", "kayit": k["kayit"]}
        self.ogrenci.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {"salon-1": 3}}})
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Reset", kayit=k["kayit"], yildiz=3, biten=1))
        self.assertEqual(self.ogretmen.iste("/api/v1/kayitlar/sifirla", {"anahtar": "#%d" % k["kayit"]})[0], 200)
        kod, c = self.ogrenci.iste("/api/v1/nabiz", nabiz("Reset", kayit=k["kayit"]))
        self.assertGreater(c["sifir"], 0)
        # öğrencinin bilgisayarındaki eski kayıt yeniden gönderilse de sıfırlanan ilerleme geri dolmaz
        kod, c = self.ogrenci.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {"salon-1": 3}}})
        self.assertEqual(c["veri"]["stars"], {})
        # sıfırlamayı öğrenmiş tarayıcının yeni kazandığı yıldızlar kaydedilir
        kod, c = self.ogrenci.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {"salon-1": 2}, "sifir": c["veri"]["sifir"]}})
        self.assertEqual(c["veri"]["stars"], {"salon-1": 2})
        self.assertEqual(sunucu.ilerleme_birlestir({"stars": {"a": 3}}, {"stars": {"b": 1}, "sifir": 5})["stars"], {"b": 1})

    # ------------------------------------------------------------ yalnızca numarayla giriş kipi
    def test_09_numara_kipi(self):
        k = self.ekle("Kayıtlı")
        self.assertEqual(self.ogrenci.iste("/api/v1/bilgi")[1]["giris_kipi"], "serbest")
        self.assertEqual(self.ogrenci.iste("/api/v1/giris-kipi", {"kip": "numara"})[0], 401)
        self.assertEqual(self.ogretmen.iste("/api/v1/giris-kipi", {"kip": "numara"})[0], 200)
        self.assertEqual(self.ogrenci.iste("/api/v1/bilgi")[1]["giris_kipi"], "numara")
        kod, c = self.ogrenci.iste("/api/v1/nabiz", nabiz("Adını Yazan"))
        self.assertTrue(c["giris_gerekli"])
        self.assertEqual(self.ogrenci.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": {"ad": "Adını Yazan"}, "veri": {"stars": {"x": 1}}})[0], 403)
        kod, c = self.ogrenci.iste("/api/v1/nabiz", nabiz("Kayıtlı", kayit=k["kayit"]))
        self.assertTrue(c["ok"])
        self.assertEqual(set(self.sinif()), {"Kayıtlı"})

    # ------------------------------------------------------------ geri bildirim: süre, takılma, yardım, çakışma
    def test_10_takilma_sure_yardim(self):
        k = self.ekle("Takılan")
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Takılan", kayit=k["kayit"], adim="salon-3"))
        self.app.db.yap("UPDATE ogrenci SET son=son-20, adim_bas=adim_bas-400")          # 20 sn önce nabız atmış, adıma 400 sn önce girmiş gibi
        hatalar = [{"tur": "hata", "adim": "salon-3", "ayrinti": {"mesaj": "afi duvara çarptı"}} for _ in range(3)] + [{"tur": "yardim", "adim": "salon-3"}]
        kod, c = self.ogrenci.iste("/api/v1/nabiz", nabiz("Takılan", kayit=k["kayit"], adim="salon-3", durum="hata", olaylar=hatalar))
        self.assertTrue(c["yardim"])
        o = self.sinif()["Takılan"]
        self.assertEqual(o["adim_hata"], 3)
        self.assertTrue(o["yardim"])
        self.assertTrue(19 <= o["sure"] <= 23, o["sure"])
        self.assertEqual((o["bugun"]["hata"], o["bugun"]["basari"]), (3, 0))
        self.assertTrue(395 <= self.ogretmen.iste("/api/v1/sinif")[1]["simdi"] - o["adim_bas"] <= 410)
        d = self.ogretmen.iste("/api/v1/ogrenci?uygulama=afi-kod&anahtar=%23" + str(k["kayit"]))[1]
        self.assertEqual(d["hatalar"][0], {"mesaj": "afi duvara çarptı", "sayi": 3})
        self.assertEqual(d["adimlar"]["salon-3"]["hata"], 3)
        self.assertEqual(len(d["gunler"]), 1)
        # öğretmen yardımı kapatır; öğrenci adımı başarınca hata sayacı sıfırlanır; yeni adımda süre baştan başlar
        self.assertEqual(self.ogretmen.iste("/api/v1/yardim-kapat", {"anahtar": "#%d" % k["kayit"]})[0], 200)
        kod, c = self.ogrenci.iste("/api/v1/nabiz", nabiz("Takılan", kayit=k["kayit"], adim="salon-3", olaylar=[{"tur": "basari", "adim": "salon-3", "ayrinti": {"yildiz": 2}}]))
        self.assertFalse(c["yardim"])
        self.assertEqual(self.sinif()["Takılan"]["adim_hata"], 0)
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Takılan", kayit=k["kayit"], adim="salon-4"))
        o = self.sinif()["Takılan"]
        self.assertLess(self.ogretmen.iste("/api/v1/sinif")[1]["simdi"] - o["adim_bas"], 5)
        # hareketsiz (boşta) geçen süre çalışma süresine eklenmez; sayfa kapanınca hemen "bağlı değil" olur
        once = o["sure"]
        self.app.db.yap("UPDATE ogrenci SET son=son-30")
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Takılan", kayit=k["kayit"], adim="salon-4", bos=600))
        self.assertEqual(self.sinif()["Takılan"]["sure"], once)
        self.assertTrue(self.sinif()["Takılan"]["cevrimici"])
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Takılan", kayit=k["kayit"], adim="salon-4", cikis=True))
        self.assertFalse(self.sinif()["Takılan"]["cevrimici"])

    def test_11_rapor_ve_disa_aktarma(self):
        a, b = self.ekle("Ada", "A sınıfı"), self.ekle("Bora", "B sınıfı")
        for k, n in ((a, 4), (b, 1)):
            self.ogrenci.iste("/api/v1/nabiz", nabiz(k["ad"], kayit=k["kayit"], adim="mutfak-2", olaylar=[{"tur": "hata", "adim": "mutfak-2", "ayrinti": {"mesaj": "m"}}] * n + [{"tur": "basari", "adim": "salon-1"}]))
        kod, r = self.ogretmen.iste("/api/v1/rapor?uygulama=afi-kod")
        self.assertEqual(r["zor_adimlar"][0], {"adim": "mutfak-2", "hata": 5, "basari": 0, "deneyen": 2, "basaran": 0})
        self.assertEqual((r["gunler"][0]["ogrenci"], r["gunler"][0]["hata"]), (2, 5))
        kod, r = self.ogretmen.iste("/api/v1/rapor?uygulama=afi-kod&sinif=A%20s%C4%B1n%C4%B1f%C4%B1")
        self.assertEqual([o["ad"] for o in r["ogrenciler"]], ["Ada"])
        self.assertEqual(r["zor_adimlar"][0]["hata"], 4)
        self.assertEqual(r["ogrenciler"][0]["toplam"], {"gun": 1, "hata": 4, "basari": 1})
        for yol in ("disa-aktar.csv", "devam.csv"):
            kod, veri = self.ogretmen.iste("/api/v1/%s?uygulama=afi-kod" % yol)
            metin = veri.decode("utf-8-sig")
            self.assertEqual(kod, 200)
            self.assertIn(a["no"] + ";Ada;A sınıfı", metin)
            self.assertIn(b["no"] + ";Bora;B sınıfı", metin)
        # sınıfa mesaj yalnızca o sınıfın öğrencisine gider
        self.ogretmen.iste("/api/v1/mesaj", {"hedef": "sinif:A sınıfı", "metin": "A'lar toplanın"})
        self.assertEqual([m["metin"] for m in self.ogrenci.iste("/api/v1/nabiz", nabiz("Ada", kayit=a["kayit"]))[1]["mesajlar"]], ["A'lar toplanın"])
        self.assertEqual(self.ogrenci.iste("/api/v1/nabiz", nabiz("Bora", kayit=b["kayit"]))[1]["mesajlar"], [])

    def test_12_ayni_adla_iki_bilgisayar_ve_robot_degisimi(self):
        self.ogrenci.iste("/api/v1/nabiz", dict(nabiz("Ali", "afi", "pc1"), cihaz={"istemci": True, "ip": "192.168.1.11"}))
        kod, c = self.ogrenci.iste("/api/v1/nabiz", dict(nabiz("Ali", "afi", "pc2"), cihaz={"istemci": True, "ip": "192.168.1.12"}))
        self.assertTrue(c["cakisma"])                      # iki ayrı bilgisayardan aynı ad + robot: uyarı
        self.assertTrue(self.sinif()["Ali"]["cakisma"])
        # başka bir "Ali" kedi robotuyla ayrı kişi; birinci Ali robotunu kediye çevirmek isterse kayıtlar karışmaz
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Ali", "pati", "pc3"))
        kod, c = self.ogrenci.iste("/api/v1/kimlik", {"uygulama": "afi-kod", "eski": {"ad": "Ali", "robot": "afi", "pid": "pc1"}, "yeni": {"ad": "Ali", "robot": "pati", "pid": "pc1"}})
        self.assertEqual(c, {"ok": False, "dolu": True})
        self.assertEqual(len(self.ogretmen.iste("/api/v1/sinif")[1]["ogrenciler"]), 2)
        # boş bir robota geçmek serbest: kayıt yeni kimliğe taşınır
        kod, c = self.ogrenci.iste("/api/v1/kimlik", {"uygulama": "afi-kod", "eski": {"ad": "Ali", "robot": "afi", "pid": "pc1"}, "yeni": {"ad": "Ali", "robot": "rover", "pid": "pc1"}})
        self.assertTrue(c["ok"])
        self.assertEqual(sorted(o["robot"] for o in self.ogretmen.iste("/api/v1/sinif")[1]["ogrenciler"]), ["pati", "rover"])

    def test_13_donem_sonu_ve_yedek(self):
        k = self.ekle("Kalan")
        self.ogrenci.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": {"ad": "Kalan", "kayit": k["kayit"]}, "veri": {"stars": {"a": 3, "b": 1}}})
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Kalan", kayit=k["kayit"]))
        self.assertEqual(self.sinif()["Kalan"]["yildiz"], 4)
        yedek = self.app.otomatik_yedek()
        self.assertTrue(os.path.isfile(yedek))
        kod, c = self.ogretmen.iste("/api/v1/temizle", {"onay": "SİL"})
        self.assertTrue(os.path.isfile(c["yedek"]))
        s = self.sinif()
        self.assertEqual((s["Kalan"]["yildiz"], s["Kalan"]["no"]), (0, k["no"]))       # ilerleme silindi, numara duruyor
        self.ogretmen.iste("/api/v1/temizle", {"onay": "SİL", "liste": True})
        self.assertEqual(self.sinif(), {})

    def test_15_ses_ayari(self):
        a, b = self.ekle("Sesli"), self.ekle("Sessiz", "Pazar")
        self.assertEqual(self.ogrenci.iste("/api/v1/nabiz", nabiz("Sesli", kayit=a["kayit"]))[1]["ses"], "acik")
        self.assertEqual(self.ogrenci.iste("/api/v1/ses", {"hedef": "*", "deger": "kapali"})[0], 401)      # öğrenci değiştiremez
        # tek öğrencinin sesi kapanır, diğeri açık kalır
        self.assertEqual(self.ogretmen.iste("/api/v1/ses", {"hedef": "#%d" % b["kayit"], "deger": "kapali"})[0], 200)
        self.assertEqual(self.ogrenci.iste("/api/v1/nabiz", nabiz("Sessiz", kayit=b["kayit"]))[1]["ses"], "kapali")
        self.assertEqual(self.ogrenci.iste("/api/v1/nabiz", nabiz("Sesli", kayit=a["kayit"]))[1]["ses"], "acik")
        s = self.sinif()
        self.assertEqual((s["Sessiz"]["ses"], s["Sessiz"]["ses_ozel"], s["Sesli"]["ses_ozel"]), ("kapali", True, False))
        # herkesin sesi kapanır: öğrenciye özel ayarlar da kalkar; misafir bilgisayar da kapalı görür
        self.ogretmen.iste("/api/v1/ses", {"hedef": "*", "deger": "kapali"})
        self.assertEqual(self.ogrenci.iste("/api/v1/nabiz", nabiz("Sesli", kayit=a["kayit"]))[1]["ses"], "kapali")
        self.assertEqual(self.ogrenci.iste("/api/v1/cihaz", {"cid": "misafir1"})[1]["ses"], "kapali")
        self.assertEqual(self.ogretmen.iste("/api/v1/sinif")[1]["ses"], "kapali")
        # sınıfa göre: yalnızca Pazar sınıfının sesi açılır
        self.ogretmen.iste("/api/v1/ses", {"hedef": "sinif:Pazar", "deger": "acik"})
        self.assertEqual((self.sinif()["Sessiz"]["ses"], self.sinif()["Sesli"]["ses"]), ("acik", "kapali"))
        self.ogretmen.iste("/api/v1/ses", {"hedef": "#%d" % b["kayit"], "deger": None})          # sınıfın genel ayarına döner
        self.assertEqual(self.sinif()["Sessiz"]["ses"], "kapali")
        self.assertEqual(self.ogretmen.iste("/api/v1/ses", {"hedef": "*", "deger": "yuksek"})[0], 400)

    def test_16_komutlar_ve_misafir_bilgisayar(self):
        k = self.ekle("Komutlu", "A")
        self.ogrenci.iste("/api/v1/nabiz", dict(nabiz("Komutlu", kayit=k["kayit"]), cid="pc-1"))
        kod, c = self.ogrenci.iste("/api/v1/cihaz", {"cid": "pc-9"})          # misafir: ilk bağlantıda eski mesaj gelmez
        self.assertEqual(c["mesajlar"], [])
        son = c["son"]
        self.assertEqual(self.ogrenci.iste("/api/v1/komut", {"hedef": "*", "komut": "duzen-sifirla"})[0], 401)
        self.assertEqual(self.ogretmen.iste("/api/v1/komut", {"hedef": "*", "komut": "format-c"})[0], 400)
        self.ogretmen.iste("/api/v1/komut", {"hedef": "*", "komut": "misafir-temizle"})
        self.ogretmen.iste("/api/v1/komut", {"hedef": "#%d" % k["kayit"], "komut": "duzen-sifirla"})
        self.ogretmen.iste("/api/v1/komut", {"hedef": "sinif:A", "komut": "liste-temizle"})
        self.ogretmen.iste("/api/v1/mesaj", {"hedef": "*", "metin": "Herkese merhaba"})
        # misafir bilgisayar herkese gidenleri alır, öğrenciye özel olanı almaz
        kod, c = self.ogrenci.iste("/api/v1/cihaz", {"cid": "pc-9", "son": son})
        self.assertEqual([(m["tur"], m["metin"]) for m in c["mesajlar"]], [("komut", "misafir-temizle"), ("mesaj", "Herkese merhaba")])
        self.assertEqual(self.ogrenci.iste("/api/v1/cihaz", {"cid": "pc-9", "son": c["son"]})[1]["mesajlar"], [])
        # öğrenci hepsini alır
        kod, c = self.ogrenci.iste("/api/v1/nabiz", dict(nabiz("Komutlu", kayit=k["kayit"]), cid="pc-1"))
        self.assertEqual([m["metin"] for m in c["mesajlar"]], ["misafir-temizle", "duzen-sifirla", "liste-temizle", "Herkese merhaba"])
        # panel: bağlı bilgisayar sayısı (misafir dahil)
        self.assertEqual(self.ogretmen.iste("/api/v1/sinif")[1]["cihaz"], {"bagli": 2, "misafir": 1})

    def test_17_bu_bilgisayarda_girenler(self):
        a, b = self.ekle("Defne"), self.ekle("Kuzey")
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Defne", kayit=a["kayit"], robot="pati"))          # bu bilgisayardan (127.0.0.1)
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Numarasız Nil", pid="x", robot="rover"))
        self.app.nabiz(nabiz("Kuzey", kayit=b["kayit"]), "10.9.9.9")                                    # başka bilgisayardan
        c = self.ogrenci.iste("/api/v1/bu-bilgisayar?uygulama=afi-kod")[1]["ogrenciler"]
        self.assertEqual(sorted((o["ad"], o["robot"], bool(o["kayit"])) for o in c), [("Defne", "pati", True), ("Numarasız Nil", "rover", False)])
        # listeden seçilen numaralı öğrenci kayıt numarasıyla girer (numarası listede görünmez)
        self.assertNotIn("no", c[0])
        kid = [o for o in c if o["ad"] == "Defne"][0]["kayit"]
        self.assertEqual(self.ogrenci.iste("/api/v1/ogrenci-giris", {"kayit": kid})[1]["kimlik"]["ad"], "Defne")
        # yalnızca numarayla giriş kipinde liste boş
        self.ogretmen.iste("/api/v1/giris-kipi", {"kip": "numara"})
        self.assertEqual(self.ogrenci.iste("/api/v1/bu-bilgisayar")[1]["ogrenciler"], [])

    def test_18_ogrenci_kendi_ilerlemesini_sifirlar(self):
        k = self.ekle("Baştan")
        o = {"ad": "Baştan", "pid": "p", "kayit": k["kayit"]}
        self.ogrenci.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {"a": 3, "b": 2}, "ws": {"a": {"x": 1}}, "last": "b", "lastN": 5}})
        self.ogrenci.iste("/api/v1/nabiz", nabiz("Baştan", kayit=k["kayit"]))
        kod, c = self.ogrenci.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {}, "ws": {}, "sifirla": 1, "sifir": 0}})
        self.assertEqual((c["veri"]["stars"], c["veri"]["ws"]), ({}, {}))
        self.assertNotIn("sifirla", c["veri"])
        self.assertGreater(c["veri"]["sifir"], time.time() - 30)
        self.assertEqual((self.sinif()["Baştan"]["yildiz"], self.sinif()["Baştan"]["biten"]), (0, 0))
        # başka bilgisayarda kalmış eski kayıt geri doldurmaz
        kod, c2 = self.ogrenci.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {"a": 3}}})
        self.assertEqual(c2["veri"]["stars"], {})
        d = self.ogretmen.iste("/api/v1/ogrenci?uygulama=afi-kod&anahtar=%23" + str(k["kayit"]))[1]
        self.assertIn("sifirla", [x["tur"] for x in d["olaylar"]])
        # birleştirme kuralları
        b = sunucu.ilerleme_birlestir
        bekleyen = b({"stars": {"a": 3}, "sifir": 5}, {"stars": {"c": 1}, "sifirla": 1, "sifir": 5})
        self.assertEqual((bekleyen["stars"], bekleyen["sifirla"]), ({"c": 1}, 1))
        self.assertEqual(b(bekleyen, {"stars": {"a": 3}, "sifir": 5})["stars"], {"c": 1})          # onay gelene kadar eski yıldızlar karışmaz
        self.assertEqual(b(bekleyen, {"stars": {"c": 1, "d": 2}, "sifirla": 1, "sifir": 5})["stars"], {"c": 1, "d": 2})      # aynı istek: sıfırlamadan sonraki çalışma birikir
        self.assertEqual(b({"stars": {"c": 1}, "sifir": 9, "sifirla_son": 1}, {"stars": {"d": 2}, "sifirla": 1})["stars"], {"c": 1, "d": 2})      # sunucu aynı isteği iki kez işlemez
        onay = b(bekleyen, {"stars": {"c": 1}, "sifir": 99})
        self.assertEqual((onay["stars"], onay["sifir"], "sifirla" in onay), ({"c": 1}, 99, False))

    def test_14_eski_veritabani_yukseltilir(self):
        """1.2 sürümünün veritabanı (yeni sütunlar yok) açılınca bozulmaz; eski öğrenciler numarasız olarak görünür."""
        yol = os.path.join(self.klasor, "eski")
        os.makedirs(yol)
        import sqlite3
        b = sqlite3.connect(os.path.join(yol, "afi-sinif.db"))
        b.executescript("""CREATE TABLE ogrenci (anahtar TEXT, uygulama TEXT, ad TEXT, robot TEXT, ip TEXT, cihaz TEXT, istemci INTEGER, ilk REAL, son REAL, adim TEXT, adim_ad TEXT,
            durum TEXT, yildiz INTEGER, biten INTEGER, son_mesaj INTEGER DEFAULT 0, oturum TEXT, PRIMARY KEY (anahtar, uygulama));
            INSERT INTO ogrenci (anahtar, uygulama, ad, robot, ip, son, yildiz, biten) VALUES ('deniz|afi', 'afi-kod', 'Deniz', 'afi', '10.0.0.5', 1, 12, 5);""")
        b.commit()
        b.close()
        app = sunucu.Sunucu(yol, port=0, sessiz=True)
        try:
            o = app.sinif({"rol": "admin"}, "afi-kod")
            self.assertEqual([(x["ad"], x["yildiz"], x["kayit"]) for x in o], [("Deniz", 12, None)])
            k = app.numara_ver("deniz|afi", "Eski sınıf")
            self.assertEqual(app.nabiz(nabiz("Deniz", pid=""), "10.0.0.5")["kimlik"]["no"], k["no"])      # 2.4 uygulaması pid göndermez
        finally:
            app.db.b.close()


class IstemciNumaraTesti(unittest.TestCase):
    """Öğrenci bilgisayarındaki istemci: numarayla giriş sunucu yokken de çalışır, kayıt karışmaz."""

    def setUp(self):
        self.klasor = tempfile.mkdtemp(prefix="afi-test-")
        self.app = sunucu.Sunucu(os.path.join(self.klasor, "sunucu"), port=0, sessiz=True)
        self.app.paketler.kur(sahte_paket(self.klasor, "2.5"))
        self.httpd = self.app.baslat()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.ist = istemci.Istemci(os.path.join(self.klasor, "istemci"), port=0)
        self.ist.ayar.update({"sunucu": "http://127.0.0.1:%d" % self.httpd.server_address[1], "tarama": False})
        self.ihttpd = self.ist.baslat(arka_plan=False)
        threading.Thread(target=self.ihttpd.serve_forever, daemon=True).start()
        self.t = Istemci("http://127.0.0.1:%d" % self.ihttpd.server_address[1])
        self.ist.bir_tur()

    def tearDown(self):
        for h in (self.ihttpd, self.httpd):
            try:
                h.shutdown()
                h.server_close()
            except OSError:
                pass
        self.app.db.b.close()
        shutil.rmtree(self.klasor, ignore_errors=True)

    def test_numarayla_giris_cevrimdisi_ve_esitleme(self):
        k = self.app.kayit_ekle("Zehra", "Cumartesi")
        self.assertTrue(self.ist.bagli())
        self.assertIn("numara", self.t.iste("/api/v1/bilgi")[1]["ozellikler"])
        kod, c = self.t.iste("/api/v1/ogrenci-giris", {"no": k["no"]})
        self.assertEqual((kod, c["kimlik"]["ad"]), (200, "Zehra"))
        kod, c = self.t.iste("/api/v1/ogrenci-giris", {"no": "999999"})
        self.assertEqual(kod, 404)
        self.assertIn("listesinde yok", c["hata"])
        o = {"ad": "Zehra", "robot": "afi", "pid": "p", "kayit": k["id"]}
        self.t.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {"salon-1": 3}}})
        # öğretmen bilgisayarı kapanır: öğrenci aynı numarayla yine girer, çalışması bu bilgisayarda saklanır
        self.httpd.shutdown()
        self.httpd.server_close()
        kod, c = self.t.iste("/api/v1/ogrenci-giris", {"no": k["no"]})
        self.assertEqual((kod, c["kimlik"]["kayit"], c.get("cevrimdisi")), (200, k["id"], True))
        self.assertEqual(self.t.iste("/api/v1/ogrenci-giris", {"no": "4711"})[0], 503)
        kod, c = self.t.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {"salon-2": 2}}})
        self.assertEqual(c["veri"]["stars"], {"salon-1": 3, "salon-2": 2})
        self.assertEqual(list(self.ist.kuyruk["kirli"]), ["#%d" % k["id"]])
        # sunucu geri gelir: bekleyen kayıt aynı öğrenciye işlenir
        app2 = sunucu.Sunucu(self.app.veri, port=0, sessiz=True)
        self.httpd = app2.baslat()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.ist.ayar["sunucu"] = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        self.ist.bir_tur()
        self.assertEqual(app2.ilerleme_oku("afi-kod", {"kayit": k["id"]})["veri"]["stars"], {"salon-1": 3, "salon-2": 2})
        self.assertEqual(self.ist.kuyruk["kirli"], {})
        app2.db.b.close()

    def test_cevrimdisi_olaylar_baska_ogrenciye_yazilmaz(self):
        a, b = self.app.kayit_ekle("Asya"), self.app.kayit_ekle("Baran")
        veri = self.app.veri
        self.httpd.shutdown()
        self.httpd.server_close()
        self.app.db.b.close()
        kod, c = self.t.iste("/api/v1/nabiz", nabiz("Asya", kayit=a["id"], olaylar=[{"tur": "hata", "adim": "salon-1", "zaman": time.time(), "ayrinti": {"mesaj": "x"}}] * 2))
        self.assertTrue(c["cevrimdisi"])
        self.app = sunucu.Sunucu(veri, port=0, sessiz=True)
        self.httpd = self.app.baslat()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.ist.ayar["sunucu"] = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        self.ist.bir_tur()
        # aynı bilgisayara Baran oturur: Asya'nın bekleyen hataları Baran'a yazılmaz
        self.t.iste("/api/v1/nabiz", nabiz("Baran", kayit=b["id"]))
        s = {o["ad"]: o for o in self.app.sinif({"rol": "admin"}, "afi-kod")}
        self.assertEqual(s["Baran"]["bugun"]["hata"], 0)
        self.t.iste("/api/v1/nabiz", nabiz("Asya", kayit=a["id"]))
        s = {o["ad"]: o for o in self.app.sinif({"rol": "admin"}, "afi-kod")}
        self.assertEqual((s["Asya"]["bugun"]["hata"], s["Baran"]["bugun"]["hata"]), (2, 0))

    def test_kalinan_adim_ve_yanlis_saat(self):
        k = self.app.kayit_ekle("Saat")
        o = {"ad": "Saat", "kayit": k["id"]}
        # yeni bilgisayarda 40 kez gezinmiş; eski bilgisayarın bayat kaydı (lastN küçük) kalınan adımı ezmez
        self.app.ilerleme_yaz({"ogrenci": o, "veri": {"stars": {"a": 1}, "last": "mutfak-9", "lastN": 40}})
        self.assertEqual(self.app.ilerleme_yaz({"ogrenci": o, "veri": {"stars": {"b": 2}, "last": "salon-1", "lastN": 3}})["veri"]["last"], "mutfak-9")
        self.assertEqual(self.app.ilerleme_yaz({"ogrenci": o, "veri": {"last": "mutfak-10", "lastN": 41}})["veri"]["last"], "mutfak-10")
        # öğrenci bilgisayarının saati 10 yıl geride: olaylar yine de bugüne yazılır ve takılma sayacına girer
        eski = time.time() - 10 * 365 * 86400
        self.app.nabiz(dict(nabiz("Saat", kayit=k["id"], adim="salon-2"), saat=eski), "10.0.0.9")
        self.app.nabiz(dict(nabiz("Saat", kayit=k["id"], adim="salon-2", olaylar=[{"tur": "hata", "adim": "salon-2", "zaman": eski + 4}]), saat=eski + 5), "10.0.0.9")
        s = self.app.sinif({"rol": "admin"}, "afi-kod")[0]
        self.assertEqual(s["adim_hata"], 1)
        z = self.app.db.tek("SELECT zaman FROM olay WHERE anahtar=?", ("#%d" % k["id"],))["zaman"]
        self.assertLess(abs(time.time() - z), 10)

    def test_cevrimdisi_sifirlama_sonra_islenir(self):
        k = self.app.kayit_ekle("Sıfır")
        o = {"ad": "Sıfır", "pid": "p", "kayit": k["id"]}
        self.t.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {"a": 3, "b": 3}}})
        veri = self.app.veri
        self.httpd.shutdown(); self.httpd.server_close(); self.app.db.b.close()
        kod, c = self.t.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {}, "ws": {}, "sifirla": 1}})
        self.assertEqual(c["veri"]["stars"], {})
        kod, c = self.t.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {"a": 1}, "sifirla": 1}})      # sıfırladıktan sonra çalışmaya devam (onay gelene kadar uygulama bayrağı gönderir)
        self.assertEqual(c["veri"]["stars"], {"a": 1})
        self.assertEqual(self.t.iste("/api/v1/bu-bilgisayar")[1]["ogrenciler"], [])
        self.app = sunucu.Sunucu(veri, port=0, sessiz=True)
        self.httpd = self.app.baslat()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.ist.ayar["sunucu"] = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        self.ist.bir_tur()
        self.assertEqual(self.app.ilerleme_oku("afi-kod", {"kayit": k["id"]})["veri"]["stars"], {"a": 1})
        yerel = self.ist.yerel_ilerleme("afi-kod", "#%d" % k["id"])
        self.assertEqual((yerel["stars"], "sifirla" in yerel), ({"a": 1}, False))

    def test_misafir_baglantisi_ve_liste(self):
        self.assertTrue(self.t.iste("/api/v1/cihaz", {"cid": "c1"})[1]["ok"])
        self.t.iste("/api/v1/nabiz", nabiz("Liste", pid="z"))
        self.assertEqual([o["ad"] for o in self.t.iste("/api/v1/bu-bilgisayar")[1]["ogrenciler"]], ["Liste"])

    def test_numara_verilince_yerel_kayit_tasinir(self):
        o = {"ad": "Umut", "robot": "afi", "pid": "pc4"}
        self.t.iste("/api/v1/ilerleme", {"uygulama": "afi-kod", "ogrenci": o, "veri": {"stars": {"salon-1": 2}}})
        self.t.iste("/api/v1/nabiz", nabiz("Umut", pid="pc4"))
        k = self.app.numara_ver("umut|afi", "Pazar")
        kod, c = self.t.iste("/api/v1/nabiz", nabiz("Umut", pid="pc4"))
        self.assertEqual(c["kimlik"]["no"], k["no"])
        self.assertEqual(self.ist.yerel_ilerleme("afi-kod", "#%d" % k["id"])["stars"], {"salon-1": 2})
        self.assertEqual(self.ist.yerel_ilerleme("afi-kod", "umut|afi"), {})
        self.assertEqual(self.ist.tanidik[k["no"]]["ad"], "Umut")


if __name__ == "__main__":
    unittest.main()
