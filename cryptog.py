from cryptography.fernet import Fernet
import socket

def generate_key():
    """
    Gera uma nova chave Fernet segura para criptografia simétrica.
    """
    return Fernet.generate_key()

def encrypt_message(message, key):
    """
    Criptografa uma mensagem de texto usando a chave fornecida.
    Retorna a mensagem criptografada ou None se falhar.
    """
    try:
        fernet = Fernet(key)
        encrypted_message = fernet.encrypt(message.encode())
        return encrypted_message
    except Exception as e:
        print(f"[Erro] Falha na criptografia: {e}")
        return None

def decrypt_message(encrypted_message, key):
    """
    Descriptografa uma mensagem criptografada com a chave fornecida.
    Retorna a string original ou uma mensagem de erro se falhar.
    """
    try:
        fernet = Fernet(key)
        decrypted_message = fernet.decrypt(encrypted_message).decode()
        return decrypted_message
    except Exception as e:
        print(f"[Erro] Falha na descriptografia: {e}")
        return "[ERRO: mensagem corrompida ou chave inválida]"

def receive_messages(conn, key):
    """
    Recebe mensagens do socket, descriptografa e imprime no terminal.
    Protegido contra falhas de conexão ou mensagens inválidas.
    """
    while True:
        try:
            encrypted_message = conn.recv(2048)
            if not encrypted_message:
                break
            message = decrypt_message(encrypted_message, key)
            print('Amigo:', message)
        except Exception as e:
            print(f"[Erro] Falha ao receber mensagem: {e}")
            break
