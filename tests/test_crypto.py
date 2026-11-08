"""
SafeRelief - Crypto Module Tests

Tes untuk semua modul kriptografi dasar.
Kriteria lulus Tahap 1 dari TASKS.md:
- Round-trip tiap algoritma
- Kunci salah gagal
- Ubah 1 byte gagal (GCM, Poly1305, HMAC)
- Kunci Vigenère salah menghasilkan teks berbeda (bukan error)
- Hash password berbeda untuk password sama
- Unwrap master key dengan password salah gagal
- Unwrap dengan token dongle salah gagal
- Unwrap hanya berhasil jika password DAN token benar
- Kunci Vigenère turunan deterministik dan semua karakter 32-126
- File pemulihan bisa dibuka dengan password pemulihan yang benar saja
"""

import pytest
import os
import tempfile
from pathlib import Path

# Import semua modul crypto
from crypto import vigenere
from crypto import aes_module
from crypto import vernam_module
from crypto import chacha_module
from crypto import hashing
from crypto import keys
from crypto import super_encrypt
import config


class TestVigenere:
    """Tes Vigenère cipher."""
    
    def test_roundtrip(self):
        """Round-trip: enkripsi lalu dekripsi menghasilkan plaintext asli."""
        plaintext = "Hello, SafeRelief! Testing Vigenere 123."
        key = "SECRETKEY"
        
        ciphertext = vigenere.encrypt(plaintext, key)
        decrypted = vigenere.decrypt(ciphertext, key)
        
        assert decrypted == plaintext
    
    def test_different_key_different_result(self):
        """Kunci Vigenère salah menghasilkan teks BERBEDA (bukan error)."""
        plaintext = "Secret Message"
        correct_key = "KEY"
        wrong_key = "WRONG"
        
        ciphertext = vigenere.encrypt(plaintext, correct_key)
        
        # Dekripsi dengan kunci salah tidak error, tapi hasil berbeda
        wrong_plaintext = vigenere.decrypt(ciphertext, wrong_key)
        assert wrong_plaintext != plaintext
    
    def test_empty_key_raises_error(self):
        """Key kosong harus raise ValueError."""
        with pytest.raises(ValueError, match="tidak boleh kosong"):
            vigenere.encrypt("test", "")
    
    def test_ascii_printable_range(self):
        """Vigenère bekerja pada ASCII 32-126."""
        # Karakter dalam rentang
        plaintext = "ABC xyz 123 !@#"
        key = "KEY"
        ciphertext = vigenere.encrypt(plaintext, key)
        decrypted = vigenere.decrypt(ciphertext, key)
        assert decrypted == plaintext
    
    def test_non_printable_unchanged(self):
        """Karakter di luar ASCII 32-126 tidak dienkripsi."""
        plaintext = "Hello\x00World"  # \x00 di luar rentang
        key = "KEY"
        ciphertext = vigenere.encrypt(plaintext, key)
        # \x00 tetap ada di posisi yang sama
        assert ciphertext[5] == '\x00'


class TestAES:
    """Tes AES-256-GCM."""
    
    def test_roundtrip(self):
        """Round-trip AES-GCM."""
        plaintext = b"Sensitive data that needs encryption"
        key = os.urandom(32)
        
        ciphertext = aes_module.encrypt(plaintext, key)
        decrypted = aes_module.decrypt(ciphertext, key)
        
        assert decrypted == plaintext
    
    def test_wrong_key_fails(self):
        """Kunci salah harus gagal dengan InvalidTag."""
        plaintext = b"Secret"
        key1 = os.urandom(32)
        key2 = os.urandom(32)
        
        ciphertext = aes_module.encrypt(plaintext, key1)
        
        # Dekripsi dengan key berbeda harus gagal
        with pytest.raises(Exception):  # cryptography.exceptions.InvalidTag
            aes_module.decrypt(ciphertext, key2)
    
    def test_tampered_data_fails(self):
        """Ubah 1 byte ciphertext harus gagal (GCM integrity)."""
        plaintext = b"Important message"
        key = os.urandom(32)
        
        ciphertext = aes_module.encrypt(plaintext, key)
        
        # Ubah 1 byte di tengah
        tampered = bytearray(ciphertext)
        tampered[20] ^= 0xFF  # Flip bits
        tampered = bytes(tampered)
        
        # Dekripsi harus gagal
        with pytest.raises(Exception):  # InvalidTag
            aes_module.decrypt(tampered, key)
    
    def test_invalid_key_length(self):
        """Key bukan 32 bytes harus raise ValueError."""
        with pytest.raises(ValueError, match="32 bytes"):
            aes_module.encrypt(b"test", b"short_key")
    
    def test_output_format(self):
        """Output format: nonce(12) + ciphertext + tag."""
        plaintext = b"test"
        key = os.urandom(32)
        ciphertext = aes_module.encrypt(plaintext, key)
        
        # Minimal: nonce(12) + plaintext(4) + tag(16) = 32 bytes
        assert len(ciphertext) >= 32


class TestVernam:
    """Tes Vernam XOR dengan keystream HKDF dan HMAC."""

    def test_roundtrip(self):
        plaintext = b"Chat message for testing"
        enc_key = os.urandom(32)
        mac_key = os.urandom(32)
        blob = vernam_module.encrypt(plaintext, enc_key, mac_key)
        assert vernam_module.decrypt(blob, enc_key, mac_key) == plaintext

    def test_same_message_uses_fresh_nonce(self):
        plaintext = b"Fresh nonce for each chat message"
        enc_key = os.urandom(32)
        mac_key = os.urandom(32)
        first = vernam_module.encrypt(plaintext, enc_key, mac_key)
        second = vernam_module.encrypt(plaintext, enc_key, mac_key)
        assert first != second
        assert first[:16] != second[:16]
        assert vernam_module.decrypt(first, enc_key, mac_key) == plaintext
        assert vernam_module.decrypt(second, enc_key, mac_key) == plaintext

    @pytest.mark.parametrize(
        "index", [0, 16, -1], ids=("nonce", "ciphertext", "hmac")
    )
    def test_tampering_nonce_ciphertext_or_hmac_fails(self, index):
        enc_key = os.urandom(32)
        mac_key = os.urandom(32)
        blob = bytearray(vernam_module.encrypt(b"tamper test", enc_key, mac_key))
        blob[index] ^= 1
        with pytest.raises(ValueError, match="HMAC verification failed"):
            vernam_module.decrypt(bytes(blob), enc_key, mac_key)

    def test_wrong_mac_key_fails(self):
        enc_key = os.urandom(32)
        blob = vernam_module.encrypt(b"authenticated", enc_key, os.urandom(32))
        with pytest.raises(ValueError, match="HMAC verification failed"):
            vernam_module.decrypt(blob, enc_key, os.urandom(32))

    def test_wrong_enc_key_is_not_detected_by_specified_hmac(self):
        plaintext = b"wrong encryption key"
        mac_key = os.urandom(32)
        enc_key = bytes(32)
        wrong_enc_key = bytes([1]) * 32
        blob = vernam_module.encrypt(plaintext, enc_key, mac_key)
        result = vernam_module.decrypt(blob, wrong_enc_key, mac_key)
        assert result != plaintext

    def test_empty_plaintext_is_rejected(self):
        with pytest.raises(ValueError, match="tidak boleh kosong"):
            vernam_module.encrypt(b"", os.urandom(32), os.urandom(32))

    def test_8161_byte_plaintext_is_rejected(self):
        with pytest.raises(ValueError, match="8160 byte"):
            vernam_module.encrypt(b"x" * 8161, os.urandom(32), os.urandom(32))

    def test_8160_byte_plaintext_is_supported(self):
        plaintext = b"x" * 8160
        enc_key = os.urandom(32)
        mac_key = os.urandom(32)
        blob = vernam_module.encrypt(plaintext, enc_key, mac_key)
        assert vernam_module.decrypt(blob, enc_key, mac_key) == plaintext

    def test_ciphertext_length_matches_plaintext_length(self):
        plaintext = b"same length"
        blob = vernam_module.encrypt(plaintext, os.urandom(32), os.urandom(32))
        assert len(blob[16:-32]) == len(plaintext)

    def test_distinct_nonces_produce_distinct_keystreams(self):
        first_plaintext = b"message number 1"
        second_plaintext = b"message number 2"
        enc_key = os.urandom(32)
        mac_key = os.urandom(32)
        first = vernam_module.encrypt(first_plaintext, enc_key, mac_key)
        second = vernam_module.encrypt(second_plaintext, enc_key, mac_key)
        assert first[:16] != second[:16]
        first_stream = bytes(
            a ^ b for a, b in zip(first[16:-32], first_plaintext)
        )
        second_stream = bytes(
            a ^ b for a, b in zip(second[16:-32], second_plaintext)
        )
        assert first_stream != second_stream

    def test_keys_must_be_32_bytes(self):
        with pytest.raises(ValueError, match="32 bytes"):
            vernam_module.encrypt(b"text", b"short", os.urandom(32))
        with pytest.raises(ValueError, match="32 bytes"):
            vernam_module.encrypt(b"text", os.urandom(32), b"short")

    def test_too_short_blob_is_rejected(self):
        with pytest.raises(ValueError, match="minimal 48 byte"):
            vernam_module.decrypt(b"\0" * 47, os.urandom(32), os.urandom(32))


class TestChaCha20:
    """Tes ChaCha20-Poly1305."""
    
    def test_roundtrip(self):
        """Round-trip ChaCha20-Poly1305."""
        plaintext = b"File content for encryption"
        key = os.urandom(32)
        
        ciphertext = chacha_module.encrypt(plaintext, key)
        decrypted = chacha_module.decrypt(ciphertext, key)
        
        assert decrypted == plaintext
    
    def test_wrong_key_fails(self):
        """Kunci salah harus gagal dengan InvalidTag."""
        plaintext = b"Encrypted file"
        key1 = os.urandom(32)
        key2 = os.urandom(32)
        
        ciphertext = chacha_module.encrypt(plaintext, key1)
        
        with pytest.raises(Exception):  # InvalidTag
            chacha_module.decrypt(ciphertext, key2)
    
    def test_tampered_data_fails(self):
        """Ubah 1 byte harus gagal (Poly1305 integrity)."""
        plaintext = b"Important file"
        key = os.urandom(32)
        
        ciphertext = chacha_module.encrypt(plaintext, key)
        
        # Ubah 1 byte
        tampered = bytearray(ciphertext)
        tampered[15] ^= 0xFF
        tampered = bytes(tampered)
        
        with pytest.raises(Exception):  # InvalidTag
            chacha_module.decrypt(tampered, key)
    
    def test_file_encryption(self):
        """Tes enkripsi/dekripsi file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Buat file test
            input_file = Path(tmpdir) / "test.txt"
            encrypted_file = Path(tmpdir) / "test.enc"
            decrypted_file = Path(tmpdir) / "decrypted.txt"
            
            original_data = b"File content for testing encryption"
            input_file.write_bytes(original_data)
            
            # Enkripsi
            key = os.urandom(32)
            chacha_module.encrypt_file(str(input_file), str(encrypted_file), key)
            
            # Dekripsi
            chacha_module.decrypt_file(str(encrypted_file), str(decrypted_file), key)
            
            # Verifikasi
            decrypted_data = decrypted_file.read_bytes()
            assert decrypted_data == original_data


class TestHashing:
    """Tes hashing (Argon2 dan SHA-256)."""
    
    def test_password_hash_different_each_time(self):
        """Hash password berbeda setiap kali (salt acak)."""
        password = "MySecurePassword123"
        
        hash1 = hashing.hash_password(password)
        hash2 = hashing.hash_password(password)
        
        # Hash berbeda (salt berbeda)
        assert hash1 != hash2
        
        # Tapi keduanya valid
        assert hashing.verify_password(password, hash1)
        assert hashing.verify_password(password, hash2)
    
    def test_password_verify_correct(self):
        """Password benar harus diverifikasi."""
        password = "CorrectPassword"
        hash_val = hashing.hash_password(password)
        
        assert hashing.verify_password(password, hash_val) is True
    
    def test_password_verify_wrong(self):
        """Password salah harus ditolak."""
        password = "CorrectPassword"
        hash_val = hashing.hash_password(password)
        
        assert hashing.verify_password("WrongPassword", hash_val) is False
    
    def test_sha256_deterministic(self):
        """SHA-256 deterministik (input sama → output sama)."""
        data = b"Test data for hashing"
        
        hash1 = hashing.sha256_hash(data)
        hash2 = hashing.sha256_hash(data)
        
        assert hash1 == hash2
        assert len(hash1) == 32  # 256 bits = 32 bytes
    
    def test_sha256_hex(self):
        """SHA-256 hex output."""
        data = b"hello"
        hash_hex = hashing.sha256_hex(data)
        
        # Hex string 64 karakter (32 bytes * 2)
        assert len(hash_hex) == 64
        assert isinstance(hash_hex, str)


class TestKeys:
    """Tes key management (wrapping, derivation, recovery)."""
    
    def test_wrap_unwrap_roundtrip(self):
        """Wrap dan unwrap master key dengan password + token benar."""
        master_key = keys.generate_master_key()
        password = "StrongPassword123"
        token = os.urandom(32)
        salt = os.urandom(16)
        
        # Wrap
        wrapped = keys.wrap_master_key(master_key, password, token, salt)
        
        # Unwrap dengan kredensial benar
        unwrapped = keys.unwrap_master_key(wrapped, password, token, salt)
        
        assert unwrapped == master_key
    
    def test_unwrap_wrong_password_fails(self):
        """Unwrap dengan password salah harus gagal."""
        master_key = keys.generate_master_key()
        correct_password = "CorrectPass"
        wrong_password = "WrongPass"
        token = os.urandom(32)
        salt = os.urandom(16)
        
        wrapped = keys.wrap_master_key(master_key, correct_password, token, salt)
        
        # Unwrap dengan password salah
        with pytest.raises(ValueError, match="password atau dongle salah"):
            keys.unwrap_master_key(wrapped, wrong_password, token, salt)
    
    def test_unwrap_wrong_token_fails(self):
        """Unwrap dengan token dongle salah harus gagal."""
        master_key = keys.generate_master_key()
        password = "Password123"
        correct_token = os.urandom(32)
        wrong_token = os.urandom(32)
        salt = os.urandom(16)
        
        wrapped = keys.wrap_master_key(master_key, password, correct_token, salt)
        
        # Unwrap dengan token salah
        with pytest.raises(ValueError, match="password atau dongle salah"):
            keys.unwrap_master_key(wrapped, password, wrong_token, salt)
    
    def test_unwrap_needs_both_factors(self):
        """Unwrap hanya berhasil jika password DAN token benar."""
        master_key = keys.generate_master_key()
        password = "Pass123"
        token = os.urandom(32)
        salt = os.urandom(16)
        
        wrapped = keys.wrap_master_key(master_key, password, token, salt)
        
        # Salah satu faktor salah → gagal
        with pytest.raises(ValueError):
            keys.unwrap_master_key(wrapped, "WrongPass", token, salt)
        
        with pytest.raises(ValueError):
            keys.unwrap_master_key(wrapped, password, os.urandom(32), salt)
        
        # Kedua faktor benar → sukses
        unwrapped = keys.unwrap_master_key(wrapped, password, token, salt)
        assert unwrapped == master_key
    
    def test_derive_key_deterministic(self):
        """Kunci turunan deterministik (master key sama → hasil sama)."""
        master_key = keys.generate_master_key()
        
        key1 = keys.derive_key(master_key, config.HKDF_LABEL_DB)
        key2 = keys.derive_key(master_key, config.HKDF_LABEL_DB)
        
        assert key1 == key2
        assert len(key1) == 32
    
    def test_derive_key_different_labels(self):
        """Label berbeda menghasilkan kunci berbeda."""
        master_key = keys.generate_master_key()
        
        db_key = keys.derive_key(master_key, config.HKDF_LABEL_DB)
        chat_key = keys.derive_key(master_key, config.HKDF_LABEL_CHAT_ENC)
        
        assert db_key != chat_key
    
    def test_vigenere_key_deterministic(self):
        """Kunci Vigenère turunan deterministik."""
        master_key = keys.generate_master_key()
        
        key1 = keys.derive_vigenere_key(master_key)
        key2 = keys.derive_vigenere_key(master_key)
        
        assert key1 == key2
    
    def test_vigenere_key_ascii_range(self):
        """Semua karakter kunci Vigenère dalam ASCII 32-126."""
        master_key = keys.generate_master_key()
        
        vig_key = keys.derive_vigenere_key(master_key)
        
        assert len(vig_key) == 16
        for char in vig_key:
            assert 32 <= ord(char) <= 126
    
    def test_recovery_file_roundtrip(self):
        """File pemulihan bisa dibuka dengan password benar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            master_key = keys.generate_master_key()
            recovery_password = "RecoveryPass123"
            recovery_path = Path(tmpdir) / "recovery.key"
            
            # Buat file recovery
            keys.create_recovery_file(master_key, recovery_password, str(recovery_path))
            
            # Buka dengan password benar
            recovered = keys.open_recovery_file(str(recovery_path), recovery_password)
            
            assert recovered == master_key
    
    def test_recovery_file_wrong_password(self):
        """File pemulihan dengan password salah harus gagal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            master_key = keys.generate_master_key()
            correct_password = "CorrectRecovery123"
            wrong_password = "WrongRecovery123"
            recovery_path = Path(tmpdir) / "recovery.key"
            
            keys.create_recovery_file(master_key, correct_password, str(recovery_path))
            
            # Buka dengan password salah
            with pytest.raises(ValueError, match="password salah atau file corrupt"):
                keys.open_recovery_file(str(recovery_path), wrong_password)
    
    def test_recovery_file_rejects_short_password(self):
        """Recovery password kurang dari 12 karakter harus ditolak."""
        with tempfile.TemporaryDirectory() as tmpdir:
            master_key = keys.generate_master_key()
            recovery_path = Path(tmpdir) / "recovery.key"
            
            # 11 karakter → harus ditolak
            with pytest.raises(ValueError, match="minimal 12 karakter"):
                keys.create_recovery_file(master_key, "Short12345!", str(recovery_path))
            
            # 12 karakter → harus diterima
            keys.create_recovery_file(master_key, "Exactly12Chr", str(recovery_path))
    
    def test_recovery_file_rejects_overwrite(self):
        """Recovery file tidak boleh ditimpa jika sudah ada."""
        with tempfile.TemporaryDirectory() as tmpdir:
            master_key = keys.generate_master_key()
            recovery_password = "RecoveryPass2024"
            recovery_path = Path(tmpdir) / "recovery.key"
            
            # Buat file pertama — harus berhasil
            keys.create_recovery_file(master_key, recovery_password, str(recovery_path))
            
            # Coba buat lagi ke path yang sama — harus ditolak
            with pytest.raises(FileExistsError):
                keys.create_recovery_file(master_key, recovery_password, str(recovery_path))
    
    def test_recovery_file_roundtrip_with_new_params(self):
        """Round-trip recovery file dengan parameter Scrypt baru (N=2^17)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            master_key = keys.generate_master_key()
            recovery_password = "StrongRecovery2024!"
            recovery_path = Path(tmpdir) / "recovery.key"
            
            keys.create_recovery_file(master_key, recovery_password, str(recovery_path))
            recovered = keys.open_recovery_file(str(recovery_path), recovery_password)
            
            assert recovered == master_key


class TestSuperEncrypt:
    """Tes super enkripsi (Vigenere + Vernam + HMAC)."""
    
    def test_roundtrip(self):
        """Round-trip super enkripsi."""
        plaintext = "Secret chat message 123!"
        vig_key = "VIGENEREKEY"
        enc_key = os.urandom(32)
        mac_key = os.urandom(32)
        
        ciphertext = super_encrypt.encrypt(plaintext, vig_key, enc_key, mac_key)
        decrypted = super_encrypt.decrypt(ciphertext, vig_key, enc_key, mac_key)
        
        assert decrypted == plaintext
    
    def test_wrong_vernam_enc_key_is_not_authenticated(self):
        """A wrong Vernam key is not detected by the specified HMAC input."""
        plaintext = "Test message"
        vig_key = "KEY"
        enc_key1 = bytes(32)
        enc_key2 = bytes([1]) * 32
        mac_key = os.urandom(32)
        
        ciphertext = super_encrypt.encrypt(plaintext, vig_key, enc_key1, mac_key)
        
        try:
            plaintext_with_wrong_key = super_encrypt.decrypt(
                ciphertext, vig_key, enc_key2, mac_key
            )
        except ValueError as exc:
            assert "Gagal decode UTF-8" in str(exc)
        else:
            assert plaintext_with_wrong_key != plaintext
    
    def test_wrong_vigenere_key_different_result(self):
        """Kunci Vigenère salah menghasilkan plaintext berbeda (bukan error)."""
        plaintext = "Original message"
        correct_vig_key = "CORRECT"
        wrong_vig_key = "WRONG"
        enc_key = os.urandom(32)
        mac_key = os.urandom(32)
        
        ciphertext = super_encrypt.encrypt(plaintext, correct_vig_key, enc_key, mac_key)
        
        # Dekripsi dengan Vigenere key salah menghasilkan teks berbeda.
        wrong_plaintext = super_encrypt.decrypt(ciphertext, wrong_vig_key, enc_key, mac_key)
        
        # Hasil berbeda dari plaintext asli (bukan error)
        assert wrong_plaintext != plaintext


# Informasi untuk pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
