"""
SafeRelief - Download Model ONNX

Script helper untuk mengunduh model YuNet dan SFace dari OpenCV Zoo.
Jalankan sekali setelah setup environment.

Usage:
    python download_models.py
"""

import urllib.request
from pathlib import Path
import sys

def download_model(filename: str, url: str, models_dir: Path) -> bool:
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
    
    if filepath.exists():
        print(f"✓ {filename} sudah ada, skip download")
        return True
    
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
        
        urllib.request.urlretrieve(url, filepath, reporthook=report_progress)
        print()  # New line after progress
        
        # Verifikasi file
        if filepath.exists() and filepath.stat().st_size > 0:
            size_mb = filepath.stat().st_size / (1024 * 1024)
            print(f"✅ {filename} berhasil diunduh ({size_mb:.1f} MB)")
            return True
        else:
            print(f"❌ {filename} gagal diunduh (file kosong)")
            if filepath.exists():
                filepath.unlink()
            return False
            
    except Exception as e:
        print(f"❌ Error saat mengunduh {filename}: {e}")
        if filepath.exists():
            filepath.unlink()
        return False

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
    
    # Model URLs (dari OpenCV Zoo)
    models = {
        "face_detection_yunet_2023mar.onnx": 
            "https://github.com/opencv/opencv_zoo/raw/master/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "face_recognition_sface_2021dec.onnx": 
            "https://github.com/opencv/opencv_zoo/raw/master/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
    }
    
    # Download setiap model
    success_count = 0
    for filename, url in models.items():
        if download_model(filename, url, models_dir):
            success_count += 1
        print()
    
    # Summary
    print("=" * 60)
    if success_count == len(models):
        print(f"✅ Semua model berhasil diunduh ({success_count}/{len(models)})")
        print()
        print("Model siap digunakan di:")
        for filename in models.keys():
            print(f"  - models/{filename}")
        print()
        print("Lanjutkan dengan: python setup_admin.py")
        return 0
    else:
        print(f"⚠️  Beberapa model gagal diunduh ({success_count}/{len(models)})")
        print()
        print("Troubleshooting:")
        print("  1. Pastikan koneksi internet stabil")
        print("  2. Coba download manual dari:")
        print("     https://github.com/opencv/opencv_zoo/tree/master/models")
        print("  3. Letakkan file .onnx di folder models/")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Download dibatalkan oleh user")
        sys.exit(1)
