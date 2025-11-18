# cliente.py - Adapted for WebSockets

import asyncio
import websockets
from cryptography.fernet import Fernet
from colorama import init, Fore, Style

init(autoreset=True)

# ========== CONFIGURAÇÕES ==========
# Para Render (WebSocket seguro):
SERVER_URI = "wss://chat-online-vj6d.onrender.com"
# Para teste local (descomente a linha abaixo):
# SERVER_URI = "ws://localhost:10000"

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
    def info(msg):
        return Fore.CYAN + msg

def validate_username(username):
    return (2 <= len(username) <= 20 and 
            not username.startswith('/') and 
            all(c.isalnum() or c in '_- ' for c in username))

async def receive_messages(websocket, chave):
    """Task para receber mensagens do servidor"""
    try:
        async for msg_criptografada in websocket:
            try:
                msg = Fernet(chave).decrypt(msg_criptografada).decode('utf-8')
                
                # Colorir diferentes tipos de mensagem
                if msg.startswith('[Sistema]'):
                    print(ColorManager.system(msg))
                elif msg.startswith('📩'):
                    print(ColorManager.info(msg))
                elif msg.startswith('👉') or msg.startswith('👋'):
                    print(ColorManager.system(msg))
                elif msg.startswith('💬'):
                    print(msg)
                else:
                    print(f"📨 {msg}")
                    
            except Exception as e:
                print(ColorManager.error(f"❌ Erro ao decifrar mensagem: {e}"))
    except websockets.exceptions.ConnectionClosed:
        print(ColorManager.error("\n📡 Conexão com o servidor foi fechada"))
    except Exception as e:
        print(ColorManager.error(f"\n💥 Erro no recebimento: {e}"))

async def main():
    print("=" * 50)
    print("💬 CLIENTE DE CHAT - RENDER.COM")
    print("=" * 50)
    
    try:
        username = input('👤 Digite seu usuário: ').strip()
        
        if not validate_username(username):
            print(ColorManager.error("❌ Nome inválido. Use 2-20 caracteres (letras, números, '-_')"))
            return
        
        print(ColorManager.info("🔗 Conectando ao servidor..."))
        
        # Configurações de conexão para Render
        async with websockets.connect(
            SERVER_URI,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10
        ) as websocket:
            
            # Receber chave como texto base64
            chave_b64 = await websocket.recv()
            chave_bytes = chave_b64.encode('utf-8')  # Converter para bytes
            cipher = Fernet(chave_bytes)
            
            print(ColorManager.success("🔑 Chave recebida do servidor"))
            
            # Enviar username criptografado
            encrypted_username = cipher.encrypt(username.encode('utf-8'))
            await websocket.send(encrypted_username)
            
            print(ColorManager.success("✅ Conectado ao servidor!"))
            print("\n" + "=" * 50)
            print("💬 CHAT INICIADO - Digite suas mensagens abaixo")
            print("=" * 50)
            print("Comandos disponíveis:")
            print("  /users       - Listar usuários online")
            print("  /pm <user> <msg> - Mensagem privada")
            print("  /sair        - Sair do chat")
            print("=" * 50)
            print()
            
            # Iniciar task para receber mensagens
            receive_task = asyncio.create_task(receive_messages(websocket, chave_bytes))
            
            try:
                while True:
                    # Ler input do usuário
                    try:
                        msg = await asyncio.get_event_loop().run_in_executor(None, input)
                    except (EOFError, KeyboardInterrupt):
                        print(ColorManager.info("\n👋 Saindo do chat..."))
                        break
                    
                    if msg.lower() == '/sair':
                        print(ColorManager.info("👋 Saindo do chat..."))
                        encrypted_msg = cipher.encrypt(msg.encode('utf-8'))
                        await websocket.send(encrypted_msg)
                        break
                    elif msg.strip():
                        # Encriptar e enviar mensagem
                        encrypted_msg = cipher.encrypt(msg.encode('utf-8'))
                        await websocket.send(encrypted_msg)
            
            except Exception as e:
                print(ColorManager.error(f"💥 Erro: {e}"))
            
            finally:
                # Fechar conexão
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass
                
    except websockets.exceptions.InvalidURI:
        print(ColorManager.error("❌ URL do servidor inválida"))
    except websockets.exceptions.ConnectionClosedError:
        print(ColorManager.error("❌ Não foi possível conectar ao servidor"))
    except asyncio.TimeoutError:
        print(ColorManager.error("⏰ Timeout ao conectar com o servidor"))
    except Exception as e:
        print(ColorManager.error(f"💥 Erro inesperado: {e}"))
    
    print(ColorManager.info("📴 Cliente finalizado"))

if __name__ == "__main__":
    asyncio.run(main())