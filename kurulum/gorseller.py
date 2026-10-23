"""Kurulum sihirbazının afi görsellerini çizer (Pillow gerekir).
Kullanım (isikcirobot_offline klasöründe, Komut İstemi; yönetici izni gerekmez):
    python kurulum/gorseller.py
Çıktı: kurulum/gorsel/ klasörü (BMP dosyaları; Inno Setup BMP ister).
"""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

KOK = os.path.dirname(os.path.abspath(__file__))
CIKTI = os.path.join(KOK, "gorsel")
YT = os.path.join(KOK, "yazitipi")

MAVI = (37, 99, 201)
MAVI_KOYU = (22, 66, 150)
MAVI_ACIK = (226, 236, 251)
LAMBA = (245, 165, 36)
LAMBA_ISIK = (255, 211, 107)
YESIL = (31, 138, 91)
MOR = (139, 111, 214)
MERCAN = (229, 115, 90)
MUREKKEP = (26, 34, 48)
BEYAZ = (255, 255, 255)


def yazi(ad, boy):
    return ImageFont.truetype(os.path.join(YT, ad), boy)


def kaydet(im, ad, boy=None):
    if boy:
        im = im.resize(boy, Image.LANCZOS)
    im.convert("RGB").save(os.path.join(CIKTI, ad), "BMP")


def robot(d, cx, cy, s, lamba=True, goz="acik", govde=True, zemin="mavi"):
    """afi robotu: cx, cy kafanın ortası, s ölçek (kafa genişliği). zemin="beyaz" ise gövde mavi çizilir."""
    BEYAZ = (255, 255, 255) if zemin == "mavi" else MAVI
    KOL = (236, 241, 248) if zemin == "mavi" else (150, 185, 235)
    w, h = s, s * 0.78
    x0, y0 = cx - w / 2, cy - h / 2
    # anten ve lamba
    d.rounded_rectangle((cx - s * .035, y0 - s * .26, cx + s * .035, y0 + 2), radius=s * .02, fill=BEYAZ)
    if lamba:
        for r, a in ((s * .19, 60), (s * .15, 110)):
            d.ellipse((cx - r, y0 - s * .32 - r, cx + r, y0 - s * .32 + r), fill=LAMBA_ISIK + (a,))
    d.ellipse((cx - s * .085, y0 - s * .405, cx + s * .085, y0 - s * .235), fill=LAMBA if lamba else (200, 200, 200))
    # gövde
    if govde:
        gw = s * .74
        d.rounded_rectangle((cx - gw / 2, y0 + h + s * .04, cx + gw / 2, y0 + h + s * .62), radius=s * .14, fill=BEYAZ)
        d.rounded_rectangle((cx - s * .16, y0 + h + s * .18, cx + s * .16, y0 + h + s * .40), radius=s * .06, fill=MAVI_ACIK)
        d.ellipse((cx - s * .06, y0 + h + s * .23, cx + s * .06, y0 + h + s * .35), fill=LAMBA)
        # kollar
        d.rounded_rectangle((cx - gw / 2 - s * .13, y0 + h + s * .10, cx - gw / 2 + s * .02, y0 + h + s * .46), radius=s * .07, fill=KOL)
        d.rounded_rectangle((cx + gw / 2 - s * .02, y0 + h + s * .10, cx + gw / 2 + s * .13, y0 + h + s * .46), radius=s * .07, fill=KOL)
    # kafa
    d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=s * .22, fill=BEYAZ)
    d.rounded_rectangle((x0 + s * .09, y0 + s * .10, x0 + w - s * .09, y0 + h - s * .10), radius=s * .16, fill=MUREKKEP)
    # gözler
    for ex in (cx - s * .19, cx + s * .19):
        if goz == "acik":
            d.ellipse((ex - s * .085, cy - s * .11, ex + s * .085, cy + s * .06), fill=(110, 200, 255))
            d.ellipse((ex - s * .03, cy - s * .07, ex + s * .02, cy - s * .02), fill=BEYAZ)
        else:            # mutlu göz
            d.arc((ex - s * .09, cy - s * .10, ex + s * .09, cy + s * .06), 200, 340, fill=(110, 200, 255), width=max(2, int(s * .04)))
    d.arc((cx - s * .13, cy - s * .02, cx + s * .13, cy + s * .17), 20, 160, fill=(110, 200, 255), width=max(2, int(s * .035)))
    # yanaklar
    for ex in (cx - s * .33, cx + s * .33):
        d.ellipse((ex - s * .04, cy + s * .04, ex + s * .04, cy + s * .10), fill=(255, 140, 150, 160))


def blok(d, x, y, w, h, renk, golge=True):
    """Blockly benzeri bulmaca bloğu (üstte çentik, altta çıkıntı)."""
    r = h * .18
    if golge:
        d.rounded_rectangle((x + 3, y + 5, x + w + 3, y + h + 5), radius=r, fill=(0, 0, 0, 45))
    d.rounded_rectangle((x, y, x + w, y + h), radius=r, fill=renk)
    n = h * .32
    d.rounded_rectangle((x + h * .45, y + h - 2, x + h * .45 + n * 1.6, y + h + n * .55), radius=n * .3, fill=renk)
    koyu = tuple(int(c * .82) for c in renk[:3])
    d.rounded_rectangle((x + h * .45, y - 1, x + h * .45 + n * 1.6, y + n * .5), radius=n * .3, fill=koyu)
    d.rounded_rectangle((x + h * .35, y + h * .38, x + w * .62, y + h * .58), radius=h * .1, fill=(255, 255, 255, 150))


def logo(d, x, y, boy, renk=BEYAZ, etiket=True):
    """'AFİ' yazısı: İ harfinin noktası sarı lamba."""
    f = yazi("fredoka-700.ttf", boy)
    d.text((x, y), "AF", font=f, fill=renk)
    gx = x + d.textlength("AF", font=f) + boy * .07
    ust = y + boy * .29
    d.rounded_rectangle((gx, ust, gx + boy * .19, y + boy * .99), radius=boy * .05, fill=renk)
    nx = gx + boy * .095
    for r, a in ((boy * .19, 70), (boy * .155, 120)):
        d.ellipse((nx - r, ust - boy * .23 - r, nx + r, ust - boy * .23 + r), fill=LAMBA_ISIK + (a,))
    d.ellipse((nx - boy * .135, ust - boy * .36, nx + boy * .135, ust - boy * .09), fill=LAMBA)
    son = gx + boy * .19
    if etiket:
        e = yazi("fredoka-700.ttf", int(boy * .30))
        tw = d.textlength("SINIF", font=e)
        et = Image.new("RGBA", (int(tw + boy * .26), int(boy * .48)), (0, 0, 0, 0))
        ed = ImageDraw.Draw(et, "RGBA")
        ed.rounded_rectangle((0, 0, et.width - 1, et.height - 1), radius=boy * .1, fill=LAMBA)
        ed.text((boy * .13, boy * .06), "SINIF", font=e, fill=MUREKKEP)
        et = et.rotate(5, expand=True, resample=Image.BICUBIC)
        return son, et
    return son, None


def arka_plan(W, H):
    im = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(im, "RGBA")
    for yy in range(H):
        t = yy / H
        d.line((0, yy, W, yy), fill=tuple(int(MAVI[i] * (1 - t) + MAVI_KOYU[i] * t) for i in range(3)) + (255,))
    # nokta ızgarası
    kat = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    kd = ImageDraw.Draw(kat, "RGBA")
    a = W / 14
    for i in range(16):
        for j in range(int(H / a) + 2):
            kd.ellipse((i * a - 2, j * a - 2, i * a + 2, j * a + 2), fill=(255, 255, 255, 28))
    return Image.alpha_composite(im, kat)


def buyuk():
    """Hoş geldiniz ve bitiş sayfalarının soldaki büyük görseli (164x314 oranında)."""
    W, H = 656, 1256
    im = arka_plan(W, H)
    kat = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(kat, "RGBA")
    random.seed(7)
    for x, y, w, renk, aci in ((-40, 470, 230, LAMBA, -12), (470, 380, 240, YESIL, 14), (430, 900, 220, MOR, -8), (-60, 1000, 200, MERCAN, 10)):
        b = Image.new("RGBA", (w + 40, 140), (0, 0, 0, 0))
        blok(ImageDraw.Draw(b, "RGBA"), 10, 20, w, 80, renk + (235,))
        b = b.rotate(aci, expand=True, resample=Image.BICUBIC)
        kat.alpha_composite(b, (x, y))
    # robotun arkasındaki ışık
    isik = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(isik, "RGBA").ellipse((W / 2 - 250, 520, W / 2 + 250, 1020), fill=(255, 255, 255, 60))
    isik = isik.filter(ImageFilter.GaussianBlur(60))
    im = Image.alpha_composite(im, isik)
    im = Image.alpha_composite(im, kat)
    d = ImageDraw.Draw(im, "RGBA")
    robot(d, W / 2, 700, 300)
    # logo
    boy = 150
    f = yazi("fredoka-700.ttf", boy)
    genislik = d.textlength("AF", font=f) + boy * .26
    son, et = logo(d, (W - genislik) / 2 - 70, 110, boy)
    im.alpha_composite(et, (int(son + 16), int(110 + boy * .50)))
    d = ImageDraw.Draw(im, "RGBA")
    alt = yazi("nunito-800.ttf", 46)
    for i, (t, a) in enumerate((("afi sınıf", 255), ("blok kodlama · sınıf sistemi", 200))):
        tw = d.textlength(t, font=alt if i == 0 else yazi("nunito-700.ttf", 38))
        d.text(((W - tw) / 2, 1090 + i * 60), t, font=alt if i == 0 else yazi("nunito-700.ttf", 38), fill=(255, 255, 255, a))
    for ad, boy in (("buyuk-100.bmp", (164, 314)), ("buyuk-150.bmp", (246, 471)), ("buyuk-200.bmp", (328, 628))):
        kaydet(im, ad, boy)
    return im


def kucuk():
    """İç sayfaların sağ üstündeki küçük görsel (55x55 oranında, beyaz zemin)."""
    S = 440
    im = Image.new("RGBA", (S, S), BEYAZ + (255,))
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((20, 20, S - 20, S - 20), radius=110, fill=MAVI)
    robot(d, S / 2, S * .60, S * .50, govde=False)
    for ad, boy in (("kucuk-100.bmp", (55, 55)), ("kucuk-150.bmp", (83, 83)), ("kucuk-200.bmp", (110, 110))):
        kaydet(im, ad, boy)
    return im


def calisan(n):
    """Kurulum sırasındaki robot: bloklar üst üste dizilir, lamba yanıp söner (n = 0..3)."""
    W, H = 640, 360
    im = Image.new("RGBA", (W, H), BEYAZ + (255,))
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((300, 300, 620, 318), radius=9, fill=(214, 221, 230))
    renkler = (LAMBA, YESIL, MOR, MERCAN)
    for i in range(n + 1):
        blok(d, 340, 238 - i * 64, 240 - i * 12, 58, renkler[i] + (255,))
    robot(d, 170, 150, 150, lamba=(n % 2 == 0), goz="acik" if n < 3 else "mutlu", zemin="beyaz")
    kaydet(im, "robot-%d.bmp" % (n + 1), (320, 180))
    return im


if __name__ == "__main__":
    os.makedirs(CIKTI, exist_ok=True)
    b = buyuk()
    k = kucuk()
    kareler = [calisan(i) for i in range(4)]
    # önizleme (yalnızca geliştirici bakar)
    on = Image.new("RGB", (328 + 20 + 640, 628), (240, 240, 240))
    on.paste(b.resize((328, 628), Image.LANCZOS).convert("RGB"), (0, 0))
    on.paste(k.resize((110, 110), Image.LANCZOS).convert("RGB"), (348, 0))
    for i, kare in enumerate(kareler):
        on.paste(kare.resize((320, 180), Image.LANCZOS).convert("RGB"), (348 + (i % 2) * 320, 130 + (i // 2) * 190))
    on.save(os.path.join(KOK, "onizleme.png"))
    print("Görseller yazıldı:", CIKTI)
