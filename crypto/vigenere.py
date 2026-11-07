"""
SafeRelief - Vigenere Cipher

Implementasi cipher Vigenère klasik untuk lapisan enkripsi pertama
dalam super enkripsi chat. Bekerja pada karakter ASCII 32-126 (95 karakter cetak).

Kenapa Vigenère:
- Demonstrasi enkripsi klasik (requirement tugas)
- Lapisan pertama sebelum Blowfish modern
- Meski lemah kriptanalisis, ini hanya lapisan demo/historis

Catatan: Karakter di luar ASCII 32-126 dibiarkan tidak terenkripsi.
"""

def encrypt(plaintext: str, key: str) -> str:
    """
    Enkripsi teks dengan Vigenère cipher.
    
    Algoritma:
    - Untuk setiap karakter plaintext dalam rentang ASCII 32-126:
      - Shift dengan karakter key yang sesuai (modulus 95)
      - Karakter di luar rentang dibiarkan apa adanya
    
    Args:
        plaintext: Teks asli
        key: Kunci Vigenère (minimal 1 karakter ASCII cetak)
    
    Returns:
        Ciphertext
    
    Raises:
        ValueError: Jika key kosong
    
    Example:
        >>> encrypt("HELLO", "KEY")
        'RIJVS'
    """
    if not key:
        raise ValueError("Vigenère key tidak boleh kosong")
    
    ciphertext = []
    key_length = len(key)
    key_index = 0  # Index untuk iterasi key (hanya maju untuk karakter yang dienkripsi)
    
    # ASCII printable range: 32 (space) sampai 126 (~)
    MIN_CHAR = 32
    MAX_CHAR = 126
    RANGE = MAX_CHAR - MIN_CHAR + 1  # 95 karakter
    
    for char in plaintext:
        char_code = ord(char)
        
        # Hanya enkripsi karakter dalam rentang ASCII cetak 32-126
        if MIN_CHAR <= char_code <= MAX_CHAR:
            # Normalisasi ke rentang 0-94
            plain_val = char_code - MIN_CHAR
            key_val = ord(key[key_index % key_length]) - MIN_CHAR
            
            # Enkripsi: (plaintext + key) mod 95
            cipher_val = (plain_val + key_val) % RANGE
            
            # Konversi kembali ke ASCII
            cipher_char = chr(cipher_val + MIN_CHAR)
            ciphertext.append(cipher_char)
            
            # Maju ke karakter key berikutnya
            key_index += 1
        else:
            # Karakter di luar rentang tidak dienkripsi
            ciphertext.append(char)
    
    return ''.join(ciphertext)


def decrypt(ciphertext: str, key: str) -> str:
    """
    Dekripsi ciphertext Vigenère.
    
    Algoritma:
    - Kebalikan dari encrypt
    - Untuk setiap karakter: shift mundur dengan key (modulus 95)
    
    Args:
        ciphertext: Teks terenkripsi
        key: Kunci Vigenère yang sama dengan saat enkripsi
    
    Returns:
        Plaintext
    
    Raises:
        ValueError: Jika key kosong
    
    Note:
        Kunci yang salah akan menghasilkan teks acak, BUKAN error.
        Ini sesuai dengan sifat Vigenère cipher.
    """
    if not key:
        raise ValueError("Vigenère key tidak boleh kosong")
    
    plaintext = []
    key_length = len(key)
    key_index = 0
    
    MIN_CHAR = 32
    MAX_CHAR = 126
    RANGE = MAX_CHAR - MIN_CHAR + 1  # 95
    
    for char in ciphertext:
        char_code = ord(char)
        
        if MIN_CHAR <= char_code <= MAX_CHAR:
            # Normalisasi
            cipher_val = char_code - MIN_CHAR
            key_val = ord(key[key_index % key_length]) - MIN_CHAR
            
            # Dekripsi: (ciphertext - key) mod 95
            plain_val = (cipher_val - key_val) % RANGE
            
            # Konversi kembali ke ASCII
            plain_char = chr(plain_val + MIN_CHAR)
            plaintext.append(plain_char)
            
            key_index += 1
        else:
            # Karakter di luar rentang tidak didekripsi
            plaintext.append(char)
    
    return ''.join(plaintext)
