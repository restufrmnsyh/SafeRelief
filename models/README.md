# Model ONNX untuk Face Recognition

Folder ini berisi model ONNX yang diperlukan untuk fitur pengenalan wajah di SafeRelief.

## Model yang Diperlukan

### 1. YuNet - Face Detection
- **File**: `face_detection_yunet_2023mar.onnx`
- **Fungsi**: Mendeteksi wajah dalam frame kamera
- **Sumber**: [OpenCV Zoo - YuNet](https://github.com/opencv/opencv_zoo/tree/master/models/face_detection_yunet)

### 2. SFace - Face Recognition
- **File**: `face_recognition_sface_2021dec.onnx`
- **Fungsi**: Menghasilkan face embedding untuk pencocokan wajah
- **Sumber**: [OpenCV Zoo - SFace](https://github.com/opencv/opencv_zoo/tree/master/models/face_recognition_sface)

## Cara Unduh

### Opsi 1: Manual Download

1. Kunjungi repository OpenCV Zoo:
   - YuNet: https://github.com/opencv/opencv_zoo/tree/master/models/face_detection_yunet
   - SFace: https://github.com/opencv/opencv_zoo/tree/master/models/face_recognition_sface

2. Download file `.onnx`:
   - `face_detection_yunet_2023mar.onnx`
   - `face_recognition_sface_2021dec.onnx`

3. Letakkan di folder ini (`models/`)

### Opsi 2: Menggunakan wget/curl (jika tersedia)

```bash
# YuNet
curl -L -o models/face_detection_yunet_2023mar.onnx https://github.com/opencv/opencv_zoo/raw/master/models/face_detection_yunet/face_detection_yunet_2023mar.onnx

# SFace
curl -L -o models/face_recognition_sface_2021dec.onnx https://github.com/opencv/opencv_zoo/raw/master/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
```

### Opsi 3: Python Script (recommended)

```python
import urllib.request
from pathlib import Path

MODELS_DIR = Path("models")
MODELS_DIR.mkdir(exist_ok=True)

models = {
    "face_detection_yunet_2023mar.onnx": 
        "https://github.com/opencv/opencv_zoo/raw/master/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": 
        "https://github.com/opencv/opencv_zoo/raw/master/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
}

for filename, url in models.items():
    filepath = MODELS_DIR / filename
    if not filepath.exists():
        print(f"Downloading {filename}...")
        urllib.request.urlretrieve(url, filepath)
        print(f"✓ {filename} downloaded")
    else:
        print(f"✓ {filename} already exists")

print("\nAll models ready!")
```

Simpan script di atas sebagai `download_models.py` di root proyek, lalu jalankan:
```bash
python download_models.py
```

## Verifikasi

Setelah download, pastikan file ada:
```bash
ls models/
```

Output yang diharapkan:
```
face_detection_yunet_2023mar.onnx
face_recognition_sface_2021dec.onnx
README.md
```

## Ukuran File

- YuNet: ~300 KB
- SFace: ~40 MB

Total: ~40 MB

## Lisensi

Model-model ini adalah bagian dari OpenCV Zoo dan tersedia di bawah lisensi Apache 2.0.

## Penggunaan dalam Proyek

Model ini akan digunakan di `auth/face_auth.py`:

```python
import cv2
import config

# Load models
detector = cv2.FaceDetectorYN.create(
    str(config.YUNET_MODEL),
    "", 
    (320, 320)
)

recognizer = cv2.FaceRecognizerSF.create(
    str(config.SFACE_MODEL),
    ""
)
```

## Troubleshooting

### Model tidak bisa di-load
- Pastikan OpenCV terinstall: `pip install opencv-python`
- Cek versi OpenCV: `python -c "import cv2; print(cv2.__version__)"`
- Minimal: OpenCV 4.8.0

### Download gagal
- Pastikan koneksi internet stabil
- Coba download manual dari browser
- Gunakan VPN jika GitHub diblokir

### File corrupt
- Hapus file dan download ulang
- Verifikasi ukuran file sesuai dengan yang tercantum di atas

---

**Catatan**: File model `.onnx` **BISA** di-commit ke git jika ukurannya tidak terlalu besar. Namun untuk file besar (>50MB), disarankan menggunakan Git LFS atau unduh terpisah saat deployment.
