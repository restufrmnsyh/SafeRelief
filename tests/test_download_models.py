"""Pengunduh harus mempertahankan model lokal jika berkas pengganti rusak."""

from pathlib import Path

from download_models import download_model


def test_failed_download_preserves_existing_model(tmp_path: Path) -> None:
    existing = tmp_path / "model.onnx"
    existing.write_bytes(b"existing")
    source = tmp_path / "incomplete"
    source.write_bytes(b"incomplete")
    assert not download_model(existing.name, source.as_uri(), tmp_path, "sha256:" + "0" * 64)
    assert existing.read_bytes() == b"existing"
    assert set(tmp_path.iterdir()) == {source, existing}
