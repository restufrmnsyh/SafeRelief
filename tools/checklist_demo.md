# Checklist Manual Demo SafeRelief

Gunakan sebelum presentasi dengan database dan dongle demo. Centang setiap
langkah setelah benar-benar dicoba di laptop presentasi.

## Uji aplikasi dan autentikasi

- [ ] **Tanpa dongle:** cabut semua dongle SafeRelief, jalankan `python app.py`.
      Pastikan halaman login tidak dapat dibuka dan aplikasi tetap di gerbang
      "Mencari dongle...".
- [ ] **Lockout login:** dengan dongle terdaftar terpasang, masukkan password
      salah tiga kali untuk satu akun. Pastikan percobaan berikutnya ditolak
      dengan pesan akun terkunci.
- [ ] **Logout saat dongle dicabut:** login dengan tiga faktor, buka dashboard,
      lalu cabut dongle. Dalam sekitar dua detik, pastikan sesi berakhir,
      aplikasi kembali ke gerbang/login dengan pesan yang sesuai, dan halaman
      terlindungi tidak lagi terbuka.

## Uji perlindungan data dan integritas

- [ ] **Ciphertext database:** buka `data/saferelief.db` menggunakan DB Browser
      for SQLite. Periksa kolom `victims.*_enc`, `users.face_encoding_enc`,
      `messages.ciphertext`, dan `users.wrapped_master_key`; pastikan isinya
      bukan plaintext yang dapat dibaca.
- [ ] **Steganografi:** sisipkan metadata pada gambar PNG, lalu verifikasi dan
      ekstrak. Pastikan metadata tampil kembali. Buat salinan gambar dan ubah
      piksel atau simpan ulang dengan kompresi; pastikan ekstraksi/verifikasi
      gambar yang diubah gagal.
- [ ] **Integritas berkas:** unggah berkas demo dan pastikan file `.enc`
      tersimpan. Salin untuk cadangan, ubah satu byte pada file terenkripsi,
      lalu coba dekripsi; pastikan gagal dan pesan kerusakan/perubahan tampil.
- [ ] **Blockchain:** catat bantuan, lalu tekan **Validasi Chain** dan pastikan
      chain valid. Pilih block non-genesis, jalankan **DEMO — Simulasi
      Tampering**, lalu validasi lagi; pastikan block rusak terdeteksi.

## Demo cadangan

- [ ] Rekam video cadangan yang menunjukkan alur utama dan hasil uji di atas.
- [ ] Simpan video, file `recovery.key`, dan cadangan database di lokasi
      terpisah dari laptop presentasi; jangan tampilkan password atau token.

## Catatan hasil

| Tanggal | Laptop presentasi | Hasil / catatan |
|---|---|---|
| | | |
