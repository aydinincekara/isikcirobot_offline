"""Görev çubuğunda, saatin yanındaki afi simgesi.

Sunucu siyah pencere olmadan, arka planda çalışır. Öğretmen simgeye tıklayınca paneli açar;
sağ tıkla AFİ KOD'u öğretmen olarak açabilir, öğrenci adresini görebilir ya da sunucuyu kapatabilir.
Simge kütüphanesi (pystray) yoksa False döner; sunucu yine çalışır, panelden kapatılabilir.
"""
import webbrowser

from . import ortak


def calistir(app, panel, httpd):
    try:
        import pystray
        from PIL import Image
    except Exception as e:      # noqa: BLE001
        app.gunluk("Görev çubuğu simgesi açılamadı: %r" % e)
        app.kapat = httpd.shutdown
        return False
    try:
        resim = Image.open(ortak.kaynak_yolu("ikon", "afi-sunucu.ico"))
    except Exception:           # noqa: BLE001
        resim = Image.new("RGB", (64, 64), (31, 138, 91))
    taban = panel.rsplit("/panel/", 1)[0]

    def uygulama_adresi():
        u = app.paketler.uygulamalar()
        return taban + "/" + (u[0]["uygulama"] + "/" if u else "")

    def ogrenci_adresi(_oge=None):
        ipler, ad = app.adresler()
        return "Öğrenci adresi: " + (ipler[0] if ipler else ad)

    def kapat(*_):
        app.gunluk("Sunucu kapatıldı")
        try:
            httpd.shutdown()
        finally:
            ikon.stop()

    def ilk(i):
        i.visible = True
        try:
            i.notify("Sunucu arka planda çalışıyor. Öğretmen paneli için saatin yanındaki afi simgesine tıklayın.", "afi sınıf")
        except Exception:       # noqa: BLE001
            pass

    menu = pystray.Menu(
        pystray.MenuItem("Öğretmen panelini aç", lambda *_: webbrowser.open(panel), default=True),
        pystray.MenuItem("AFİ KOD'u aç (öğretmen)", lambda *_: webbrowser.open(uygulama_adresi())),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(ogrenci_adresi, lambda *_: webbrowser.open(panel + "#ayarlar"), enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sunucuyu kapat", kapat),
    )
    ikon = pystray.Icon("afi-sinif", resim, "afi sınıf sunucusu çalışıyor", menu)
    app.kapat = kapat
    ikon.run(setup=ilk)
    return True
