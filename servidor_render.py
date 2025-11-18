# servidor.py - Adapted for WebSockets and Render.com deployment

import asyncio
import os
import signal
import sys
import time
import websockets
from cryptography.fernet import Fernet
from colorama import init, Fore, Style

# Inicialização do colorama
init(autoreset=True)

# ========== CONFIGURAÇÕES ==========
PORT = int(os.environ.get("PORT", 10000))

# ========== GERENCIADOR DE CORES ==========
class ColorManager:
    @staticmethod
    def system(msg):
        return Fore.MAGENTA + Style.BRIGHT + msg
    
    @staticmethod
    def error(msg):
        return Fore.RED + msg
    
    @staticmethod
    def success(msg):
        return Fore.GREEN + msg
    
    @staticmethod
    def warning(msg):
        return Fore.YELLOW + msg
    
    @staticmethod
    def info(msg):
        return Fore.CYAN + msg

# ========== ESTADO GLOBAL ==========
clients = {}
clients_lock = asyncio.Lock()

# Chave FIXA para evitar problemas de transmissão
CHAVE_SECRETA = Fernet.generate_key()
print("=" * 60)
print("🚀 INICIANDO SERVIDOR DE CHAT - RENDER.COM")
print("=" * 60)
print(f"🔑 Chave FIXA gerada: {CHAVE_SECRETA.decode()[:50]}...")
print(f"🌐 Porta: {PORT}")
print("=" * 60)

def validate_username(username):
    return (2 <= len(username) <= 20 and 
            not username.startswith('/') and 
            all(c.isalnum() or c in '_- ' for c in username))

async def send_system_message(websocket, message):
    try:
        encrypted_msg = Fernet(CHAVE_SECRETA).encrypt(f"[Sistema] {message}".encode())
        await websocket.send(encrypted_msg)
    except:
        pass

async def broadcast_message(message_str, skip_ws=None):
    if not clients:
        return
        
    encrypted_msg = Fernet(CHAVE_SECRETA).encrypt(message_str.encode())
    
    async with clients_lock:
        current_clients = list(clients.keys())
    
    for ws in current_clients:
        if ws != skip_ws:
            try:
                await ws.send(encrypted_msg)
            except:
                async with clients_lock:
                    if ws in clients:
                        del clients[ws]

async def handler(websocket, path):
    client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
    print(f"📡 Nova conexão de: {client_ip}")
    
    try:
        # ENVIAR CHAVE PRIMEIRO - como texto base64 para evitar corrupção
        chave_b64 = CHAVE_SECRETA.decode('utf-8')
        await websocket.send(chave_b64)
        print(f"🔑 Chave enviada para {client_ip}")

        # Receber username criptografado
        encrypted_username = await asyncio.wait_for(websocket.recv(), timeout=30.0)
        
        # Tentar descriptografar
        try:
            username = Fernet(CHAVE_SECRETA).decrypt(encrypted_username).decode('utf-8').strip()
            print(f"✅ Login bem-sucedido: {username}")
        except Exception as e:
            print(f"❌ Falha na descriptografia de {client_ip}: {e}")
            await websocket.close(1008, "Erro de autenticação")
            return
        
        if not validate_username(username):
            await websocket.close(1008, "Nome de usuário inválido")
            return

        # Verificar duplicata
        async with clients_lock:
            if any(data["username"].lower() == username.lower() for data in clients.values()):
                await websocket.close(1008, "Nome já está em uso")
                return

            # Registrar cliente
            clients[websocket] = {
                "username": username,
                "ip": client_ip,
                "join_time": time.time()
            }
            user_count = len(clients)

        print(f"🎉 {username} conectou-se ({user_count} usuários online)")

        # Mensagem de boas-vindas
        await broadcast_message(f"👉 {username} entrou no chat", websocket)
        await send_system_message(websocket, f"Bem-vindo(a) {username}! {user_count} usuários online.")
        await send_system_message(websocket, "Comandos: /users, /pm <user> <msg>, /sair")

        # Loop principal de mensagens
        async for encrypted_msg in websocket:
            try:
                msg = Fernet(CHAVE_SECRETA).decrypt(encrypted_msg).decode('utf-8').strip()
                
                if msg.lower() == '/sair':
                    break
                elif msg.lower() == '/users':
                    async with clients_lock:
                        user_list = ", ".join([data["username"] for data in clients.values()])
                    await send_system_message(websocket, f"👥 Online ({len(clients)}): {user_list}")
                elif msg.lower().startswith('/pm '):
                    parts = msg.split(' ', 2)
                    if len(parts) < 3:
                        await send_system_message(websocket, "Uso: /pm <usuário> <mensagem>")
                        continue
                    
                    target_user = parts[1]
                    pm_msg = parts[2]
                    
                    # Encontrar usuário alvo
                    target_ws = None
                    target_username = None
                    async with clients_lock:
                        for ws, data in clients.items():
                            if data["username"].lower() == target_user.lower():
                                target_ws = ws
                                target_username = data["username"]
                                break
                    
                    if target_ws and target_ws != websocket:
                        await send_system_message(target_ws, f"📩 {username} para você: {pm_msg}")
                        await send_system_message(websocket, f"📩 Você para {target_username}: {pm_msg}")
                    else:
                        await send_system_message(websocket, f"Usuário '{target_user}' não encontrado")
                else:
                    # Mensagem normal
                    async with clients_lock:
                        if websocket in clients:
                            await broadcast_message(f"💬 {username}: {msg}", websocket)
                            
            except Exception as e:
                print(f"❌ Erro processando mensagem de {username}: {e}")
                break

    except asyncio.TimeoutError:
        print(f"⏰ Timeout na autenticação de {client_ip}")
    except websockets.exceptions.ConnectionClosed:
        print(f"📡 Conexão fechada durante handshake: {client_ip}")
    except Exception as e:
        print(f"💥 Erro no handler para {client_ip}: {e}")
    finally:
        # Remover cliente
        async with clients_lock:
            if websocket in clients:
                username = clients[websocket]["username"]
                del clients[websocket]
                user_count = len(clients)
                print(f"👋 {username} desconectou ({user_count} usuários restantes)")
                await broadcast_message(f"👋 {username} saiu do chat", None)

async def health_check(path, request_headers):
    """Health check para o Render"""
    if path == "/health" or path == "/healthz":
        return 200, [], b"OK"
    return None

async def main():
    print("🔄 Iniciando servidor WebSocket...")
    
    # Configurações para Render
    start_server = websockets.serve(
        handler,
        "0.0.0.0",
        PORT,
        ping_interval=20,
        ping_timeout=20,
        process_request=health_check
    )

    print(f"✅ Servidor iniciado na porta {PORT}")
    print("🔗 URLs para conexão:")
    print(f"   Local: ws://localhost:{PORT}")
    print(f"   Render: wss://chat-online-vj6d.onrender.com")
    print("📡 Aguardando conexões...")

    await start_server
    
    # Manter o servidor rodando
    await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Servidor interrompido")
    except Exception as e:
        print(f"💥 Erro fatal: {e}")