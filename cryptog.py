# cryptog.py - Remains largely the same, but adapted for Fernet usage in context
from cryptography.fernet import Fernet

def generate_key():
    return Fernet.generate_key()

# encrypt_message and decrypt_message are now handled inline with Fernet, but you can keep if needed.