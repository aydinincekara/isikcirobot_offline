"""afi sınıf - sunucu ve öğrenci istemcisinin ortak parçaları.

Yalnızca Python'un standart kütüphanesi kullanılır; bu sayede hem .py olarak hem de PyInstaller ile
tek dosyalık .exe olarak ek kurulum gerektirmeden çalışır.
"""
import hashlib
import ipaddress
import json
import mimetypes
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler

PLATFORM_SURUM = "1.2.0"
SISTEM = "afi-sinif"
VARSAYILAN_PORT = 8000
ISTEMCI_PORT = 8100
GUNCELLEME_ADRESI = "https://aydinincekara.github.io/isikcirobot_offline/version.json"
MANIFEST = "afi-paket.json"

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/woff2", ".woff2")


# ---------------------------------------------------------------- yollar
def donduruldu():
    """PyInstaller ile .exe yapıldıysa True."""
    return bool(getattr(sys, "frozen", False))


def program_klasoru():
    if donduruldu():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def kaynak_yolu(*parcalar):
    """Program içine gömülü dosyalar (panel, ilk paket)."""
    taban = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "_MEIPASS", None):
        taban = os.path.join(taban, "afi_sinif")
    return os.path.join(taban, *parcalar)


def kurulum_bilgisi():
    """Kurulum sihirbazının programın yanına yazdığı kurulum.json: rol, veri klasörü, port, sunucu adresi...
    Program kurulumsuz (USB'den, Python ile) çalışıyorsa boş döner."""
    yol = os.path.join(program_klasoru(), "kurulum.json")
    try:
        with open(yol, "r", encoding="utf-8-sig") as f:      # Inno Setup UTF-8'i BOM ile yazar
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def windows_kullanici():
    """Bilgisayarda oturum açmış kullanıcının adı (ör. ogrenci1)."""
    for ad in ("USERNAME", "USER", "LOGNAME"):
        if os.environ.get(ad):
            return os.environ[ad]
    try:
        import getpass
        return getpass.getuser()
    except Exception:          # noqa: BLE001 - ad bulunamazsa önemli değil
        return ""


def _guvenli_ad(ad):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in (ad or "kullanici"))[:40] or "kullanici"


def eski_kayitlari_tasi(hedef, adaylar, isaret):
    """Eski sürümlerin kayıt klasörünü yeni yere kopyalar (hedefte 'isaret' dosyası yoksa).
    Eski klasör silinmez, adı '-tasindi' ile biter: bir sorun olursa elle geri alınabilir."""
    if os.path.exists(os.path.join(hedef, isaret)):
        return None
    for eski in adaylar:
        if not eski or os.path.normcase(os.path.abspath(eski)) == os.path.normcase(os.path.abspath(hedef)):
            continue
        if os.path.isfile(os.path.join(eski, isaret)):
            try:
                shutil.copytree(eski, hedef, dirs_exist_ok=True)
                try:
                    os.replace(eski, eski.rstrip("\\/") + "-tasindi")
                except OSError:
                    pass
                return eski
            except OSError:
                return None
    return None


def veri_klasoru(rol):
    """Kayıtların tutulduğu klasör. Öncelik: AFI_VERI ortam değişkeni > kurulumda seçilen klasör > varsayılan.
    Kurulumla (varsayılan C:\afikod):  C:\afikod\kayitlar\sunucu   ve   C:\afikod\kayitlar\istemci\<Windows kullanıcısı>
    Kurulumsuz sunucu: programın yanındaki 'afi-sunucu-veri' (taşınabilir).
    Kurulumsuz istemci: %LOCALAPPDATA%\afi-sinif\veri."""
    yol = os.environ.get("AFI_VERI")
    k = kurulum_bilgisi()
    yerel = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    eskiler = []
    if not yol:
        if rol == "sunucu":
            if k.get("veri"):
                yol = os.path.expandvars(str(k["veri"]))
            elif k:
                yol = os.path.join(program_klasoru(), "kayitlar", "sunucu")
            else:
                yol = os.path.join(program_klasoru(), "afi-sunucu-veri")
            if k:      # 1.0 ve 1.1 sürümlerinin kayıt yerleri
                eskiler = [os.path.join(yerel, "afi-sinif", "sunucu-veri"), os.path.join(program_klasoru(), "afi-sunucu-veri")]
                if os.environ.get("ProgramData"):
                    eskiler.append(os.path.join(os.environ["ProgramData"], "afi-sinif", "sunucu-veri"))
        else:
            if k:
                taban = os.path.expandvars(str(k.get("veri_istemci") or os.path.join(program_klasoru(), "kayitlar", "istemci")))
                yol = os.path.join(taban, _guvenli_ad(windows_kullanici()))
                eskiler = [os.path.join(yerel, "afi-sinif", "veri")]
            else:
                yol = os.path.join(yerel, "afi-sinif", "veri")
    os.makedirs(yol, exist_ok=True)
    if eskiler:
        eski = eski_kayitlari_tasi(yol, eskiler, "afi-sinif.db" if rol == "sunucu" else "ayarlar.json")
        if eski:
            try:
                with open(os.path.join(yol, "gunluk.txt"), "a", encoding="utf-8") as f:
                    f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "Eski kayıtlar taşındı: " + eski + "\n")
            except OSError:
                pass
    return yol


def uyari(baslik, metin):
    """Penceresiz çalışırken kullanıcıya hata göstermek için (Windows ileti kutusu)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, metin, baslik, 0x30)
            return
        except Exception:      # noqa: BLE001
            pass
    try:
        print(baslik + ": " + metin)
    except Exception:          # noqa: BLE001
        pass


# ---------------------------------------------------------------- küçük yardımcılar
def simdi():
    return time.time()


def surum_parca(s):
    out = []
    for p in str(s or "0").replace("-", ".").split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def daha_yeni(a, b):
    """a sürümü b'den yeni mi?"""
    return surum_parca(a) > surum_parca(b)


def sha256_dosya(yol):
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(1 << 16), b""):
            h.update(parca)
    return h.hexdigest()


def json_oku(yol, varsayilan=None):
    try:
        with open(yol, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return varsayilan


def json_yaz(yol, veri):
    """Önce geçici dosyaya yazar, sonra yerine koyar: elektrik kesilse de dosya bozulmaz."""
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=1)
    os.replace(gecici, yol)


TR_KUCUK = str.maketrans({"I": "i", "İ": "i", "ı": "i"})   # DENIZ, Deniz, DENİZ hepsi aynı kişi


def anahtar_yap(ad, robot):
    """Öğrenci kimliği: takma ad + robot. Aynı adlı iki öğrenci farklı robot seçerse ayrı kişidir."""
    ad = " ".join(str(ad or "").translate(TR_KUCUK).lower().split())[:40]
    return ad + "|" + (str(robot or "afi")[:20])


# ---------------------------------------------------------------- ağ
def yerel_ipler():
    """Bu bilgisayarın yerel ağ adresleri (192.168.x.x gibi)."""
    ipler = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("10.255.255.255", 1))     # paket gönderilmez; sadece hangi arayüzün kullanılacağı öğrenilir
        ipler.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for bilgi in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = bilgi[4][0]
            if ip not in ipler:
                ipler.append(ip)
    except OSError:
        pass
    return [ip for ip in ipler if not ip.startswith("127.")] or ["127.0.0.1"]


def bilgisayar_adi():
    try:
        return socket.gethostname()
    except OSError:
        return "?"


def aralikta(ip, araliklar):
    """ip, '192.168.1.0/24' ya da '192.168.1.10-192.168.1.40' gibi aralıklardan birinde mi?"""
    try:
        adr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if adr.is_loopback:
        return True
    for a in araliklar or []:
        a = str(a).strip()
        if not a:
            continue
        try:
            if "-" in a:
                bas, son = [ipaddress.ip_address(x.strip()) for x in a.split("-", 1)]
                if bas <= adr <= son:
                    return True
            elif adr in ipaddress.ip_network(a, strict=False):
                return True
        except ValueError:
            continue
    return False


def aralik_gecerli(a):
    try:
        if "-" in a:
            [ipaddress.ip_address(x.strip()) for x in a.split("-", 1)]
        else:
            ipaddress.ip_network(a.strip(), strict=False)
        return True
    except ValueError:
        return False


_YEREL_ACICI = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # yerel ağda vekil sunucu kullanılmaz


def http_json(url, veri=None, zaman_asimi=3.0, yerel=True, yontem=None):
    """JSON isteği gönderir, JSON cevap döner. Hata olursa OSError/ValueError fırlatır."""
    govde = None if veri is None else json.dumps(veri).encode("utf-8")
    istek = urllib.request.Request(url, data=govde, method=yontem or ("POST" if govde is not None else "GET"))
    istek.add_header("Content-Type", "application/json")
    istek.add_header("User-Agent", SISTEM + "/" + PLATFORM_SURUM)
    acici = _YEREL_ACICI if yerel else urllib.request.build_opener()
    with acici.open(istek, timeout=zaman_asimi) as cevap:
        return json.loads(cevap.read().decode("utf-8") or "null")


def http_indir(url, hedef, zaman_asimi=60.0, yerel=False, ilerleme=None):
    istek = urllib.request.Request(url, headers={"User-Agent": SISTEM + "/" + PLATFORM_SURUM})
    acici = _YEREL_ACICI if yerel else urllib.request.build_opener()
    with acici.open(istek, timeout=zaman_asimi) as cevap, open(hedef, "wb") as f:
        while True:
            parca = cevap.read(1 << 16)
            if not parca:
                break
            f.write(parca)
            if ilerleme:
                ilerleme(len(parca))
    return hedef


# ---------------------------------------------------------------- uygulama paketleri
class PaketHatasi(Exception):
    pass


class PaketDeposu:
    """Uygulama paketleri (afi-kod gibi). Her sürüm ayrı klasörde durur; hangisinin kullanıldığı aktif.json'da yazar.
    paketler/
      aktif.json                 {"afi-kod": "2.2"}
      afi-kod/2.2/index.html ...
      _zip/afi-kod-2.2.zip       (istemcilere dağıtmak için orijinal paket)
    """

    def __init__(self, kok):
        self.kok = kok
        os.makedirs(os.path.join(kok, "_zip"), exist_ok=True)
        self.kilit = threading.Lock()

    def _aktif_dosya(self):
        return os.path.join(self.kok, "aktif.json")

    def aktifler(self):
        return json_oku(self._aktif_dosya(), {}) or {}

    def aktif(self, uyg):
        s = self.aktifler().get(uyg)
        if not s:
            return None, None
        yol = os.path.join(self.kok, uyg, s)
        return (s, yol) if os.path.isdir(yol) else (None, None)

    def surumler(self, uyg):
        d = os.path.join(self.kok, uyg)
        if not os.path.isdir(d):
            return []
        return sorted([x for x in os.listdir(d) if os.path.isfile(os.path.join(d, x, MANIFEST))], key=surum_parca)

    def manifest(self, uyg, surum=None):
        surum = surum or self.aktif(uyg)[0]
        if not surum:
            return None
        return json_oku(os.path.join(self.kok, uyg, surum, MANIFEST))

    def uygulamalar(self):
        out = []
        for uyg, s in sorted(self.aktifler().items()):
            m = self.manifest(uyg, s) or {}
            z = self.zip_yolu(uyg, s)
            out.append({"uygulama": uyg, "ad": m.get("ad", uyg), "surum": s, "giris": m.get("giris", "index.html"),
                        "sha256": sha256_dosya(z) if os.path.isfile(z) else None, "boyut": os.path.getsize(z) if os.path.isfile(z) else None,
                        "surumler": self.surumler(uyg)})
        return out

    def zip_yolu(self, uyg, surum):
        return os.path.join(self.kok, "_zip", "%s-%s.zip" % (uyg, surum))

    def kur(self, zip_yol, beklenen_sha=None, etkinlestir=True):
        """Paketi doğrular ve açar. Döner: manifest."""
        with self.kilit:
            if beklenen_sha and sha256_dosya(zip_yol).lower() != beklenen_sha.lower():
                raise PaketHatasi("Paketin doğrulama özeti tutmuyor (indirme bozuk ya da paket değiştirilmiş).")
            try:
                z = zipfile.ZipFile(zip_yol)
            except zipfile.BadZipFile:
                raise PaketHatasi("Dosya geçerli bir zip paketi değil.")
            with z:
                try:
                    m = json.loads(z.read(MANIFEST).decode("utf-8"))
                except KeyError:
                    raise PaketHatasi("Pakette %s yok." % MANIFEST)
                uyg, surum = str(m.get("uygulama", "")), str(m.get("surum", ""))
                if not uyg or not surum or "/" in uyg + surum or "\\" in uyg + surum or ".." in uyg + surum:
                    raise PaketHatasi("Paket bilgisi eksik ya da hatalı.")
                hedef = os.path.join(self.kok, uyg, surum)
                gecici = tempfile.mkdtemp(prefix="kur-", dir=self.kok)
                try:
                    kok_gercek = os.path.realpath(gecici)
                    for ad in z.namelist():
                        yol = os.path.realpath(os.path.join(gecici, ad))
                        if not (yol == kok_gercek or yol.startswith(kok_gercek + os.sep)):
                            raise PaketHatasi("Pakette güvensiz dosya yolu var: " + ad)
                    z.extractall(gecici)
                    if os.path.isdir(hedef):
                        shutil.rmtree(hedef)
                    os.makedirs(os.path.dirname(hedef), exist_ok=True)
                    os.replace(gecici, hedef)
                finally:
                    if os.path.isdir(gecici):
                        shutil.rmtree(gecici, ignore_errors=True)
            zh = self.zip_yolu(uyg, surum)
            if os.path.abspath(zip_yol) != os.path.abspath(zh):
                shutil.copyfile(zip_yol, zh)
            if etkinlestir:
                self._sec(uyg, surum)
            return m

    def _sec(self, uyg, surum):
        a = self.aktifler()
        a[uyg] = surum
        json_yaz(self._aktif_dosya(), a)

    def sec(self, uyg, surum):
        with self.kilit:
            if surum not in self.surumler(uyg):
                raise PaketHatasi("Bu sürüm kurulu değil: " + surum)
            self._sec(uyg, surum)

    def temizle(self, uyg, sakla=3):
        """En yeni 'sakla' sürümü ve aktif olanı bırakır, eskileri siler."""
        with self.kilit:
            aktif = self.aktifler().get(uyg)
            hepsi = self.surumler(uyg)
            silinecek = [s for s in hepsi[:-sakla] if s != aktif]
            for s in silinecek:
                shutil.rmtree(os.path.join(self.kok, uyg, s), ignore_errors=True)
                try:
                    os.remove(self.zip_yolu(uyg, s))
                except OSError:
                    pass
            return silinecek

    def gomulu_paketleri_kur(self):
        """Program içinde gelen paketleri (ilk kurulum) kurar; daha yeni sürüm zaten varsa dokunmaz."""
        klasor = kaynak_yolu("paketler")
        if not os.path.isdir(klasor):
            return []
        kurulan = []
        for ad in sorted(os.listdir(klasor)):
            if not ad.endswith(".zip"):
                continue
            yol = os.path.join(klasor, ad)
            try:
                with zipfile.ZipFile(yol) as z:
                    m = json.loads(z.read(MANIFEST).decode("utf-8"))
            except (KeyError, ValueError, zipfile.BadZipFile):
                continue
            mevcut = self.aktif(m["uygulama"])[0]
            if m["surum"] in self.surumler(m["uygulama"]) or (mevcut and not daha_yeni(m["surum"], mevcut)):
                continue
            self.kur(yol)
            kurulan.append(m["uygulama"] + " " + m["surum"])
        return kurulan


# ---------------------------------------------------------------- HTTP temel sınıfı
class Hata(Exception):
    def __init__(self, kod, mesaj):
        Exception.__init__(self, mesaj)
        self.kod = kod
        self.mesaj = mesaj


class TemelIsleyici(BaseHTTPRequestHandler):
    server_version = SISTEM + "/" + PLATFORM_SURUM
    protocol_version = "HTTP/1.1"
    EN_BUYUK_GOVDE = 4 * 1024 * 1024

    def log_message(self, bicim, *args):       # konsolu doldurmasın; sunucu kendi günlüğünü tutar
        g = getattr(self.server, "gunluk", None)
        if g:
            g(self.client_address[0] + " " + (bicim % args))

    def istemci_ip(self):
        return self.client_address[0].replace("::ffff:", "")

    def yerelden_mi(self):
        try:
            return ipaddress.ip_address(self.istemci_ip()).is_loopback
        except ValueError:
            return False

    def govde(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > self.EN_BUYUK_GOVDE:
            self.close_connection = True
            raise Hata(413, "İstek çok büyük.")
        self._govde_okundu = True
        return self.rfile.read(n) if n else b""

    def parse_request(self):
        self._govde_okundu = False          # aynı bağlantıda her istek için yeniden
        return BaseHTTPRequestHandler.parse_request(self)

    def send_response(self, code, message=None):
        # Okunmamış istek gövdesi bağlantıda kalırsa (keep-alive) sonraki isteği bozar: önce boşalt.
        if not getattr(self, "_govde_okundu", False) and getattr(self, "headers", None) is not None:
            self._govde_okundu = True
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n > self.EN_BUYUK_GOVDE:
                self.close_connection = True
            elif n:
                try:
                    self.rfile.read(n)
                except OSError:
                    self.close_connection = True
        BaseHTTPRequestHandler.send_response(self, code, message)

    def json_govde(self):
        ham = self.govde()
        if not ham:
            return {}
        try:
            v = json.loads(ham.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise Hata(400, "Geçersiz JSON.")
        if not isinstance(v, dict):
            raise Hata(400, "JSON nesnesi bekleniyordu.")
        return v

    def gonder(self, kod, govde, tur="application/json; charset=utf-8", basliklar=None):
        if isinstance(govde, (dict, list)) or govde is None:
            govde = json.dumps(govde, ensure_ascii=False).encode("utf-8")
        elif isinstance(govde, str):
            govde = govde.encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("Cache-Control", "no-store" if tur.startswith("application/json") else "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (basliklar or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(govde)

    def json_gonder(self, veri, kod=200, basliklar=None):
        self.gonder(kod, veri, basliklar=basliklar)

    def yonlendir(self, yer):
        self.send_response(302)
        self.send_header("Location", yer)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def dosya_gonder(self, kok, yol):
        """kok klasörü içindeki dosyayı gönderir (klasör dışına çıkmaya izin vermez)."""
        kok_gercek = os.path.realpath(kok)
        yol = yol.split("?", 1)[0].split("#", 1)[0]
        yol = urllib.request.url2pathname(yol).lstrip("/\\")
        tam = os.path.realpath(os.path.join(kok_gercek, yol))
        if not (tam == kok_gercek or tam.startswith(kok_gercek + os.sep)):
            raise Hata(403, "Erişim yok.")
        if os.path.isdir(tam):
            tam = os.path.join(tam, "index.html")
        if not os.path.isfile(tam):
            raise Hata(404, "Bulunamadı.")
        tur = mimetypes.guess_type(tam)[0] or "application/octet-stream"
        if tur.startswith("text/") or tur in ("application/json", "image/svg+xml"):
            tur += "; charset=utf-8"
        boyut = os.path.getsize(tam)
        self.send_response(200)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(boyut))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Last-Modified", self.date_time_string(int(os.path.getmtime(tam))))
        self.end_headers()
        if self.command != "HEAD":
            with open(tam, "rb") as f:
                shutil.copyfileobj(f, self.wfile)

    def hata_gonder(self, kod, mesaj):
        try:
            self.json_gonder({"hata": mesaj}, kod)
        except OSError:
            pass
