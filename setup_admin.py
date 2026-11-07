"""
SafeRelief - Setup Admin Awal

Skrip ini dijalankan SEKALI untuk membuat admin pertama.
Akan menolak jalan jika admin sudah ada.

Langkah:
1. Init database
2. Input username/password (min 8 karakter)
3. Hash password dengan Argon2
4. Provision dongle (tulis token ke flashdisk)
5. Tangkap wajah dari webcam (5 frame)
6. Generate master key organisasi
7. Bungkus master key dengan KEK (dari password + token dongle)
8. Buat file recovery.key untuk pemulihan
9. Simpan data admin ke database
10. Catat ADMIN_BOOTSTRAP ke activity_log

Eksekusi bersifat atomik: jika gagal di tengah, tidak ada yang tersimpan.

Catatan: Placeholder untuk Tahap 4 (Autentikasi).
"""

import sys
import getpass
from pathlib import Path

def main():
    """
    Setup admin pertama kali.
    """
    print("SafeRelief - Setup Admin Awal")
    print("=" * 50)
    print()
    print("Skrip ini akan membuat admin pertama.")
    print("PERINGATAN: Hanya bisa dijalankan SATU KALI.")
    print()
    print("Status: Belum siap (modul autentikasi belum diimplementasikan)")
    print()
    print("Untuk melanjutkan:")
    print("1. Selesaikan Tahap 1-3 terlebih dahulu")
    print("2. Kemudian jalankan skrip ini dengan modul yang lengkap")
    print("=" * 50)

if __name__ == "__main__":
    main()
