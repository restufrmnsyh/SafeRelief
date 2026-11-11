"""Masked password input helpers for Windows CLI bootstrap flows.

Trade-off: menampilkan "*" untuk tiap karakter mengurangi tingkat penyembunyian
karena panjang password terlihat, tetapi ini dipilih untuk kemudahan verifikasi
ketika mengetik di terminal Windows yang bersifat visual. Tujuannya tetap agar
password tidak terlihat secara utuh seperti saat input biasa.
"""

from __future__ import annotations

import getpass
import sys

try:
    import msvcrt
except ImportError:  # pragma: no cover - hanya terjadi di non-Windows
    msvcrt = None


def read_masked_password(prompt: str) -> str:
    """Baca password secaratersembunyi di Windows, dengan masking per karakter.

    Fungsi ini memakai `msvcrt.getwch()` untuk membaca karakter satu per satu tanpa
    menunggu Enter. Setiap karakter ditampilkan sebagai "*" di terminal. Backspace
    menghapus karakter terakhir dari buffer dan tampilan, dan Enter mengakhiri input.
    Jika dijalankan di non-Windows, fungsi otomatis fallback ke `getpass.getpass()`
    demi kompatibilitas.
    """
    if msvcrt is None:
        print(
            "Info: mode non-Windows terdeteksi; menggunakan input password standar "
            "getpass() sebagai fallback.",
            file=sys.stderr,
        )
        return getpass.getpass(prompt)

    chars: list[str] = []
    print(prompt, end="", flush=True)

    try:
        while True:
            key = msvcrt.getwch()

            if key in ("\r", "\n"):
                print("", flush=True)
                return "".join(chars)

            if key == "\x03":
                raise KeyboardInterrupt

            if key in ("\b", "\x7f"):
                if chars:
                    chars.pop()
                    print("\b \b", end="", flush=True)
                continue

            if key in ("\x00", "\xe0"):
                _ = msvcrt.getwch()
                continue

            if ord(key) < 32 and key not in ("\t",):
                continue

            chars.append(key)
            print("*", end="", flush=True)
    except KeyboardInterrupt:
        print("", flush=True)
        raise
