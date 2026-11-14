# Arah visual dashboard SafeRelief

Referensi: gambar dashboard Hireism yang diberikan pengguna pada 14 November 2026.
Lingkup: dashboard PySide6 dan, atas permintaan lanjutan pengguna, seluruh sembilan halaman menu beserta dialognya. Alur autentikasi dan fungsi halaman memakai implementasi yang ada.

Reading this as: dashboard koordinasi untuk admin dan relawan bencana, dengan sidebar putih dan ruang kerja lavender, dial ENERGY 2 / RHYTHM 2 / MOTION 1.

- Warna: indigo `#4F50D9` untuk panel sambutan dan fokus, mengikuti referensi dan memusatkan perhatian pada pekerjaan lapangan.
- Permukaan: putih dan lavender `#F6F5FC` memisahkan navigasi, area kerja, dan konteks sesi tanpa gradient, glow, atau blur.
- Tipografi: Segoe UI karena tersedia di Windows dan terbaca pada tabel maupun kontrol desktop.
- Tata letak: sidebar berkelompok menuju fitur yang sudah ada; area utama berisi status korban dan sebaran posko; panel kanan berisi konteks sesi dan akses koordinasi.
- Fokus: panel sambutan dengan jumlah korban menjadi penekanan utama; kartu status putih dibuat seragam untuk membandingkan ukuran yang sama.
- Jarak: skala 4/8/12/16/24/32; jarak besar memisahkan bagian, jarak kecil menghubungkan judul dengan data.
- Radius: panel 16 px, kartu status 12 px, tombol 8 px; inisial pengguna memakai lingkaran.
- Aset: nama produk sebagai teks dan inisial akun nyata, tanpa logo baru, foto stok, atau ilustrasi generatif.
- Navigasi: pilihan aktif memakai bidang lavender dan huruf tebal; label dan menu mengikuti peran pengguna.
- Hierarki sidebar: kelompok menjadi tombol dropdown 12 px tebal dengan panah buka/tutup dan target 44 px; tujuan 13 px reguler diberi indentasi. Data lapangan terbuka saat awal, kelompok lain tertutup agar sidebar ringkas.
- Menu sempit: kelompok yang sama menjadi submenu native Qt, dengan tujuan dan pembatasan peran yang sama seperti sidebar.
- Data: angka dari `get_dashboard_summary`; tidak menambah tren, jadwal, atau aktivitas rekaan.
- Tema: terang sesuai referensi untuk membaca tabel operasional; tidak menambah toggle tema.
- Ukuran: tiga kolom di jendela lebar; konteks berpindah di bawah konten pada lebar sedang; di bawah 720 px sidebar menjadi menu berlabel yang bisa dibuka dengan keyboard.
- Motion: hanya hover, pressed, focus; tanpa animasi berulang.
- Aksesibilitas: kontrol minimal 44 px, fokus indigo, label eksplisit, teks biasa untuk nama akun, dan pengukuran kontras.

## Penerapan pada halaman menu

- Sidebar dropdown tetap tersedia pada setiap menu agar pengguna tidak perlu kembali ke dashboard untuk berpindah fitur; kelompok halaman aktif terbuka otomatis.
- Panel putih di atas lavender menjaga kesinambungan dengan dashboard; judul halaman dan tindakan utama menggantikan banner sambutan yang hanya relevan pada dashboard.
- Pencarian dan filter memakai label tetap agar fungsinya terbaca setelah pengguna mengetik.
- Kolom utama tabel mengisi sisa ruang; kolom bertombol menyediakan tambahan ruang untuk padding agar Decrypt/Unduh tidak terpotong.
- Tabel lebar seperti blockchain dapat digulir di dalam panelnya; seluruh halaman tetap mengikuti lebar viewport.
- Dokumentasi foto memisahkan daftar dan preview, sehingga pilihan foto dan metadata dapat ditinjau bersamaan.
- Bantuan memisahkan formulir pencatatan dari riwayat pada jendela lebar; pada jendela sempit keduanya ditumpuk.
- Chat membatasi tinggi panel baca dan mempertahankan scrollbar internal agar area kirim tetap mudah dijangkau.
- Ciphertext memakai Consolas untuk memudahkan pembacaan karakter; judul dan teks operasional tetap Segoe UI.
- Formulir dialog memakai bidang putih, judul tegas, serta tombol Simpan/Batal di luar area gulir agar tetap dapat dijangkau.
- Tidak menambahkan ilustrasi, foto profil, angka contoh pada data organisasi, atau mekanisme autentikasi baru.
- Popup informasi/peringatan/error/konfirmasi memakai stylesheet lokal dengan permukaan putih agar tidak mewarisi transparansi halaman; tombol dan pilihan default tetap native Qt.
- Daftar pilihan dropdown memakai permukaan putih dan warna seleksi kontras agar teks tetap terbaca ketika popup terpisah dari halaman induknya.
- Formulir memakai selector `formDialog` yang terpisah dari dashboard, dengan latar putih opaque, judul 22 px, keterangan singkat, dan tinggi yang mengikuti jumlah field agar formulir pendek tidak menyisakan ruang berlebihan.

Arah ini menjadi acuan halaman berikutnya setelah dashboard disetujui pengguna.
