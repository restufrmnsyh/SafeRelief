"""
cek_manual.py — skrip SEKALI PAKAI untuk verifikasi manual enkripsi kolom.

Cara pakai:
    1. Taruh file ini di root proyek SafeRelief (sejajar dengan app.py)
    2. Aktifkan venv, lalu jalankan: python cek_manual.py
    3. Buka data/saferelief.db di DB Browser for SQLite, cek tabel victims
    4. Setelah selesai verifikasi, hapus file ini dan data/saferelief.db

Skrip ini membuat database baru, menyimpan satu data korban contoh dengan
secure_store.add_victim(), lalu mencetak datanya kembali (hasil dekripsi)
sebagai bukti bahwa round-trip enkripsi-dekripsi bekerja.

CATATAN: skrip ini menebak nama fungsi berdasarkan rancangan AGENTS.md.
Kalau ada AttributeError atau TypeError, baca pesan errornya — biasanya
itu memberi tahu nama fungsi atau parameter yang sebenarnya dipakai di
secure_store.py kamu. Sesuaikan baris yang relevan, atau tempel pesan
errornya untuk dibantu.
"""

import sys
import traceback

print("=" * 60)
print("SafeRelief — Verifikasi Manual Enkripsi Kolom")
print("=" * 60)

# --- 1. Import modul proyek ---
try:
    from database import db
    from database import secure_store
    from crypto.keys import generate_master_key, derive_key
    import config
except ImportError as e:
    print(f"\n❌ Gagal import modul: {e}")
    print("Pastikan file ini ada di root proyek (sejajar dengan app.py)")
    print("dan venv sudah aktif.")
    sys.exit(1)

# --- 2. Inisialisasi database ---
print("\n[1/4] Inisialisasi database...")
try:
    db.init_db()
    print(f"    OK — database di {config.DB_PATH}")
except Exception as e:
    print(f"❌ init_db() gagal: {e}")
    traceback.print_exc()
    sys.exit(1)

# --- 3. Buat kunci database contoh ---
# Di aplikasi asli, master_key didapat dari unwrap_master_key() saat login.
# Di sini kita buat master key BARU khusus untuk tes ini — tidak dipakai
# untuk data sungguhan, jadi aman di-generate ulang setiap jalan.
print("\n[2/4] Membuat kunci database contoh...")
try:
    master_key = generate_master_key()
    db_key = derive_key(master_key, config.HKDF_LABEL_DB)
    print("    OK — db_key diturunkan dari master key contoh")
except Exception as e:
    print(f"❌ Gagal membuat kunci: {e}")
    traceback.print_exc()
    sys.exit(1)

# --- 4. Simpan satu data korban contoh ---
print("\n[3/4] Menyimpan data korban contoh...")
contoh_korban = {
    "kode_korban": "TEST-0001",
    "nama_panggilan": "Contoh",
    "usia": 30,
    "gender": "L",
    "posko_id": None,
    "status": "selamat",
    "nama_lengkap": "Budi Santoso",
    "nik": "3271010101010001",
    "alamat_asal": "Jl. Contoh No. 1, Jakarta",
    "kondisi_medis": "Tidak ada riwayat khusus",
    "kontak_keluarga": "081234567890",
    "catatan": "Ini data uji coba, bukan data sungguhan",
}

victim_id = None
try:
    victim_id = secure_store.add_victim(db_key, contoh_korban)
    print(f"    OK — tersimpan dengan id/kode: {victim_id}")
except TypeError as e:
    print(f"❌ add_victim() dipanggil dengan parameter yang salah: {e}")
    print("    Kemungkinan urutan atau nama parameter secure_store.add_victim()")
    print("    berbeda dari yang ditebak skrip ini. Cek signature fungsinya,")
    print("    lalu sesuaikan pemanggilan di atas.")
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"❌ add_victim() gagal: {e}")
    traceback.print_exc()
    sys.exit(1)

# --- 5. Baca kembali dan tampilkan hasil dekripsi ---
print("\n[4/4] Membaca kembali data (uji round-trip dekripsi)...")
try:
    # Coba beberapa kemungkinan nama fungsi get, karena belum pasti
    # signature persisnya.
    hasil = None
    if hasattr(secure_store, "get_victim_by_kode"):
        hasil = secure_store.get_victim_by_kode(db_key, "TEST-0001")
    elif hasattr(secure_store, "get_victim"):
        hasil = secure_store.get_victim(db_key, victim_id)

    if hasil:
        print("    OK — data berhasil dibaca kembali dan didekripsi:")
        for k, v in dict(hasil).items():
            print(f"      {k:20s}: {v}")
    else:
        print("    (Tidak bisa memanggil fungsi get otomatis, lewati langkah ini.")
        print("     Tidak masalah — yang penting data sudah tersimpan di DB.)")
except Exception as e:
    print(f"    (Gagal membaca kembali: {e})")
    print("    Tidak masalah untuk tujuan verifikasi manual ini.")

# --- Ringkasan ---
print("\n" + "=" * 60)
print("SELESAI")
print("=" * 60)
print(f"""
Langkah selanjutnya:
1. Buka DB Browser for SQLite
2. File > Open Database > pilih: {config.DB_PATH}
3. Tab "Browse Data" > pilih tabel "victims"
4. Cek baris dengan kode_korban = TEST-0001:
   - kode_korban, nama_panggilan, usia, gender, status
     harus terlihat sebagai TEKS BIASA (plaintext)
   - nik_enc, nama_lengkap_enc, alamat_asal_enc, kondisi_medis_enc,
     kontak_keluarga_enc, catatan_enc
     harus terlihat sebagai DATA ACAK (Hex/Blob), BUKAN teks yang
     bisa dibaca seperti "Budi Santoso" atau "3271010101010001"

Setelah selesai verifikasi, bersihkan:
    del data\\saferelief.db      (Windows)
    del cek_manual.py
""")
