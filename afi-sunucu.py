"""afi sınıf sunucusu (öğretmen bilgisayarı).
Python ile çalıştırmak için bu klasörde Komut İstemi'nde:  python afi-sunucu.py
(Python kurmadan çalışan hali: afi-sunucu.exe)"""
import sys

from afi_sinif.sunucu import calistir

if __name__ == "__main__":
    sys.exit(calistir())
