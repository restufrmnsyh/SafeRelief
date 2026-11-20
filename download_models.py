"""
SafeRelief - Download Model ONNX

Unduh YuNet dan SFace untuk pendaftaran dan login.
Jalankan sekali setelah setup environment.

Usage:
    python download_models.py
"""

import hashlib
import sys
import urllib.request
from pathlib import Path
from tempfile import NamedTemporaryFile

def download_model(filename: str, url: str, models_dir: Path, checksum: str = "") -> bool:
    """
    Download model file dari URL.
    
    Args:
        filename: Nama file model
        url: URL download
        models_dir: Path ke folder models
    
    Returns:
        True jika berhasil, False jika gagal
    """
    filepath = models_dir / filename
    
    def matches(path: Path) -> bool:
        if not path.is_file() or not path.stat().st_size:
            return False
        if not checksum:
            return True
        algorithm, digest = checksum.split(":")
        with path.open("rb") as source:
            return hashlib.file_digest(source, algorithm).hexdigest() == digest

    if matches(filepath):
        print(f"✓ {filename} sudah ada, skip download")
        return True
    
    temporary = None
    try:
        print(f"📥 Mengunduh {filename}...")
        print(f"   URL: {url}")
        
        # Download dengan progress
        def report_progress(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                percent = min(downloaded * 100 / total_size, 100)
                mb_downloaded = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(f"\r   Progress: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)", end='')
        
        with NamedTemporaryFile(dir=models_dir, delete=False) as target:
            temporary = Path(target.name)
        urllib.request.urlretrieve(url, temporary, reporthook=report_progress)
        print()  # New line after progress
        
        # Verifikasi file
        if matches(temporary):
            temporary.replace(filepath)
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"✅ {filename} berhasil diunduh ({size_mb:.1f} MB)")
            return True
        else:
            print(f"❌ {filename} kosong atau checksum tidak cocok")
            return False
            
    except Exception as e:
        print(f"❌ Error saat mengunduh {filename}: {e}")
        return False
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def main():
    """
    Main function untuk download semua model.
    """
    print("SafeRelief - Download Model ONNX")
    print("=" * 60)
    print()
    
    # Setup paths
    base_dir = Path(__file__).parent
    models_dir = base_dir / "models"
    models_dir.mkdir(exist_ok=True)
    
    files = {
        "face_detection_yunet_2023mar.onnx": 
            "https://github.com/opencv/opencv_zoo/raw/master/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "face_recognition_sface_2021dec.onnx": 
            "https://github.com/opencv/opencv_zoo/raw/master/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    }
    checksums = {
        "face_detection_yunet_2023mar.onnx": "sha256:8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "face_recognition_sface_2021dec.onnx": "sha256:0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    }
    
    # Download setiap model
    success_count = 0
    for filename, url in files.items():
        if download_model(filename, url, models_dir, checksums[filename]):
            success_count += 1
        print()
    
    # Summary
    print("=" * 60)
    if success_count == len(files):
        print("✅ Model YuNet dan SFace tersedia.")
        print()
        print("Model siap digunakan di:")
        for filename in files:
            print(f"  - models/{filename}")
        print()
        print("Jalankan python app.py. Untuk instalasi baru, buat admin dengan python setup_admin.py dahulu.")
        return 0
    else:
        print(f"⚠️  Berkas tersedia: {success_count}/{len(files)}")
        print()
        print("Troubleshooting:")
        print("  1. Pastikan koneksi internet stabil")
        print("  2. Coba unduh ulang dari URL berkas yang gagal.")
        print("  3. Letakkan file .onnx di folder models/")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Download dibatalkan oleh user")
        sys.exit(1)
