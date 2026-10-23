"""Kurulum sihirbazının yazdığı kurulum.json'un okunması."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from afi_sinif import ortak  # noqa: E402


class KurulumTesti(unittest.TestCase):
    def setUp(self):
        self.k = tempfile.mkdtemp(prefix="afi-kurulum-")
        self.yama = mock.patch.object(ortak, "program_klasoru", lambda: self.k)
        self.yama.start()
        self.eski_env = os.environ.pop("AFI_VERI", None)

    def tearDown(self):
        self.yama.stop()
        if self.eski_env is not None:
            os.environ["AFI_VERI"] = self.eski_env
        shutil.rmtree(self.k, ignore_errors=True)

    def yaz(self, veri):
        with open(os.path.join(self.k, "kurulum.json"), "w", encoding="utf-8-sig") as f:      # BOM'lu, Inno Setup gibi
            json.dump(veri, f, ensure_ascii=False)

    def test_kurulumsuz(self):
        self.assertEqual(ortak.kurulum_bilgisi(), {})
        self.assertEqual(ortak.veri_klasoru("sunucu"), os.path.join(self.k, "afi-sunucu-veri"))

    def test_kurulumlu_sunucu(self):
        veri = os.path.join(self.k, "Öğretmen verileri")
        self.yaz({"rol": "sunucu", "veri": veri, "port": 8001, "ad": "Bilgi Evi 1"})
        self.assertEqual(ortak.kurulum_bilgisi()["port"], 8001)
        self.assertEqual(ortak.veri_klasoru("sunucu"), veri)
        self.assertTrue(os.path.isdir(veri))

    def test_bozuk_dosya(self):
        with open(os.path.join(self.k, "kurulum.json"), "w") as f:
            f.write("{bozuk")
        self.assertEqual(ortak.kurulum_bilgisi(), {})

    def test_varsayilan_kayitlar_klasoru_ve_tasima(self):
        self.yaz({"rol": "sunucu", "port": 8000})
        eski = os.path.join(self.k, "yerel", "afi-sinif", "sunucu-veri")
        os.makedirs(eski)
        with open(os.path.join(eski, "afi-sinif.db"), "w") as f:
            f.write("eski")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": os.path.join(self.k, "yerel")}):
            yol = ortak.veri_klasoru("sunucu")
        self.assertEqual(yol, os.path.join(self.k, "kayitlar", "sunucu"))
        with open(os.path.join(yol, "afi-sinif.db")) as f:
            self.assertEqual(f.read(), "eski")
        self.assertTrue(os.path.isdir(eski + "-tasindi"), "eski klasör yedek olarak kalır")
        self.assertIn("taşındı", open(os.path.join(yol, "gunluk.txt"), encoding="utf-8").read())

    def test_istemci_kullaniciya_gore(self):
        self.yaz({"rol": "istemci", "veri_istemci": os.path.join(self.k, "kayitlar", "istemci")})
        with mock.patch.dict(os.environ, {"USERNAME": "öğrenci 1", "LOCALAPPDATA": os.path.join(self.k, "yok")}):
            yol = ortak.veri_klasoru("istemci")
        self.assertEqual(os.path.dirname(yol), os.path.join(self.k, "kayitlar", "istemci"))
        self.assertTrue(os.path.basename(yol).startswith("öğrenci"))


if __name__ == "__main__":
    unittest.main()
