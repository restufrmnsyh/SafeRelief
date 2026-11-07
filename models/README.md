# Model ONNX untuk Face Recognition

Folder ini berisi model ONNX yang diperlukan untuk fitur pengenalan wajah.

## Status

| File | Ukuran | Status |
|------|--------|--------|
| `face_detection_yunet_2023mar.onnx` | ~227 KB | **Sudah tersedia** |
| `face_recognition_sface_2021dec.onnx` | ~37 MB | **Perlu diunduh manual** |

---

## Cara Unduh SFace (wajib untuk face recognition)

### Opsi 1 – Browser (paling mudah)

Buka link berikut di browser, klik tombol **Download**:

```
https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
```

Simpan file ke folder `models/` di root proyek SafeRelief.

### Opsi 2 – Python (jalankan dari root proyek)

```bash
python download_models.py
```

Script tersebut sudah ada di root proyek dan menangani kedua model.

### Opsi 3 – Git LFS / clone langsung

```bash
# Clone hanya folder model dari OpenCV Zoo
git clone --depth 1 --filter=blob:none --sparse \
    https://github.com/opencv/opencv_zoo.git /tmp/opencv_zoo
cd /tmp/opencv_zoo
git sparse-checkout set models/face_recognition_sface
copy models\face_recognition_sface\face_recognition_sface_2021dec.onnx \
     <path_ke_SafeRelief>\models\
```

---

## Verifikasi

Setelah download, jalankan:

```bash
python -c "
import cv2, config
r = cv2.FaceRecognizerSF.create(str(config.SFACE_MODEL), '')
print('SFace OK')
d = cv2.FaceDetectorYN.create(str(config.YUNET_MODEL), '', (320, 320))
print('YuNet OK')
"
```

Output yang diharapkan:
```
SFace OK
YuNet OK
```

---

## Sumber Resmi

- **YuNet**: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
- **SFace**: https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface
- **Lisensi**: Apache 2.0

## Catatan untuk Tes

`tests/test_face_auth.py` **tidak memerlukan** model ONNX atau webcam fisik —
semua tes unit menggunakan embedding buatan (numpy array acak) dan mock.

Untuk tes manual dengan webcam asli, gunakan:
```bash
python tools/test_face_cli.py
```
