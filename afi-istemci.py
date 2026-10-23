"""afi sınıf öğrenci istemcisi (öğrenci bilgisayarı).
Python ile çalıştırmak için bu klasörde Komut İstemi'nde:  python afi-istemci.py
(Python kurmadan çalışan hali: afi-istemci.exe; ilk açılışta kendini kurar)"""
import sys

from afi_sinif.istemci import calistir

if __name__ == "__main__":
    sys.exit(calistir())
