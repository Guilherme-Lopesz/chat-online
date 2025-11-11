import threading
import socket
import json
import os
import sys
from cryptog import encrypt_message, decrypt_message
from colorama import init, Fore, Style
init(autoreset=True)

LOBBY_FILE = 'lobby.json'
lobby_lock = threading.RLock()

def read_lobby():
    with lobby_lock:
        if not os.path.exists(LOBBY_FILE):
            return []
        try:
            with open(LOBBY_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []

def print_help_menu():
    print(Fore.CYAN + "\n--- Central de Ajuda ---\n")
    print(Style.BRIGHT + "Este programa ('cliente.py') permite que você entre em chats.")
    print(Style.BRIGHT + "\nComandos disponíveis DENTRO de um chat:")
    print(Fore.GREEN + "  /help         " + Style.RESET_ALL + "- Mostra esta ajuda dentro do chat.")
    print(Fore.GREEN + "  /sair         " + Style.RESET_ALL + "- Desconecta do chat atual.")
    print(Fore.GREEN + "  /users        " + Style.RESET_ALL + "- Lista os usuários online.")
    print(Fore.GREEN + "  /info         " + Style.RESET_ALL + "- Mostra dados da sala.")
    print(Fore.GREEN + "  /pm <user> <msg>" + Style.RESET_ALL + "- Envia uma mensagem privada.")
    print(Fore.GREEN + "  /togglepm     " + Style.RESET_ALL + "- Bloqueia/desbloqueia PMs.")
    print(Fore.GREEN + "  /votekick <user>" + Style.RESET_ALL + "- Votação para expulsar usuário.")
    print(Fore.GREEN + "  /votemute <user>" + Style.RESET_ALL + "- Votação para silenciar usuário.")
    print(Fore.GREEN + "  /vote <yes/no>" + Style.RESET_ALL + "- Vota numa votação ativa.")
    print(Fore.CYAN + "------------------------")
    input(Style.DIM + "\nPressione <Enter> para voltar ao menu...\n")

def main():
    while True:
        print(Style.BRIGHT + Fore.GREEN + "\n" + "="*40)
        print("🎪 CHAT TERMINAL - MENU PRINCIPAL")
        print("="*40)
        print("1: Entrar em Chat Público (Local)")
        print("2: Entrar em Chat Remoto (IP/Domínio)")
        print("3: Entrar em Chat Render.com")
        print("4: Ajuda e Instruções")
        print("5: Sair")
        print("="*40)
        
        choice = input(Fore.WHITE + "Escolha: ")

        host_para_conectar = 'localhost'
        porta_para_conectar = None
        SENHA = None

        if choice == '1':
            # ... (código original para chats locais)
            continue
            
        elif choice == '2':
            # ... (código original para IP personalizado)
            continue
            
        elif choice == '3':
            try:
                print(Fore.CYAN + "\n🌐 CONEXÃO RENDER.COM")
                host_para_conectar = input("URL do Render (ex: meuchat.onrender.com): ").strip()
                if not host_para_conectar:
                    print(Fore.RED + "❌ URL é obrigatória")
                    continue
                
                # Remove https:// se o usuário colocar
                host_para_conectar = host_para_conectar.replace('https://', '').replace('http://', '')
                
                porta_para_conectar = 50001  # Porta padrão do Render
                SENHA = input("Senha (Enter se não tiver): ")
                
                print(Fore.GREEN + f"🔗 Conectando a {host_para_conectar}:{porta_para_conectar}...")
                
            except Exception as e:
                print(Fore.RED + f"❌ Erro na configuração: {e}")
                continue

        elif choice == '4':
            print_help_menu()
            continue

        elif choice == '5':
            print(Fore.GREEN + "\n👋 Até logo!")
            sys.exit()
        else:
            print(Fore.RED + "❌ Opção inválida")
            continue

        if not porta_para_conectar:
            continue

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(10.0)

        try:
            print(f"\n🔗 Conectando a {host_para_conectar}:{porta_para_conectar}...")
            client.connect((host_para_conectar, porta_para_conectar))
            client.settimeout(None)

            if SENHA is not None:
                client.send(SENHA.encode('utf-8'))

            initial_response = client.recv(9)
            if initial_response == b"FAIL     ": 
                print(Fore.RED + "\n[Erro] Senha incorreta. Conexão recusada\n")
                client.close()
                continue
            elif initial_response == b"FAIL_FULL":
                print(Fore.RED + "\n[Erro] A sala está cheia\n")
                client.close()
                continue

            remaining_bytes_needed = 44 - len(initial_response)
            if remaining_bytes_needed > 0:
                client.settimeout(2.0)
                key_bytes_remaining = client.recv(remaining_bytes_needed)
                client.settimeout(None)
                CHAVE_BYTES = initial_response + key_bytes_remaining
            else:
                CHAVE_BYTES = initial_response

            if len(CHAVE_BYTES) != 44:
                print(Fore.RED + "[Erro] Chave de criptografia incompleta")
                client.close()
                continue

            username = input('Usuário> ')
            encrypted = encrypt_message(username, CHAVE_BYTES)
            if encrypted:
                client.send(encrypted)
            else:
                print(Fore.RED + "[Erro] Falha ao criptografar nome de usuário")
                client.close()
                continue

            client.settimeout(5.0)
            auth_status = client.recv(9)
            client.settimeout(None)

            if auth_status == b"FAIL_NAME":
                print(Fore.RED + f"\n[Erro] O nome '{username}' já está em uso nesta sala\n")
                client.close()
                continue
            elif auth_status != b"OK_NAME  ":
                print(Fore.RED + f"\n[Erro] Resposta inesperada: {auth_status}\n")
                client.close()
                continue

        except ConnectionRefusedError:
            print(Fore.RED + f"\n[Erro] Ninguém está ouvindo em {host_para_conectar}:{porta_para_conectar}\n")
            continue
        except socket.timeout:
            print(Fore.RED + f"\n[Erro] Tempo limite ao conectar\n")
            client.close()
            continue
        except Exception as e:
            print(Fore.RED + f"\n[Erro crítico] {e}\n")
            client.close()
            continue

        print(Fore.GREEN + "\n--- Conectado ao Chat ---\nDigite '/help' para ver os comandos")

        global stop_threads
        stop_threads = False

        thread = threading.Thread(target=receiveMessages, args=[client, CHAVE_BYTES])
        thread2 = threading.Thread(target=sendMessages, args=[client, CHAVE_BYTES])
        thread.start()
        thread2.start()
        thread.join()
        thread2.join()

        print(Style.BRIGHT + "\nDesconectado. Voltando ao menu...\n")

def receiveMessages(client, chave):
    global stop_threads
    while not stop_threads:
        try:
            msg_criptografada = client.recv(2048)
            if not msg_criptografada:
                print(Fore.YELLOW + '\n[Info] O servidor fechou a sala\n')
                stop_threads = True
                break

            msg = decrypt_message(msg_criptografada, chave)
            if not msg: continue  # ignora mensagem quebrada

            if msg.startswith('<'): 
                parts = msg.split('>', 1)
                if len(parts) == 2:
                    print(Fore.WHITE + Style.BRIGHT + parts[0] + '>' + Style.NORMAL + parts[1] + '\n')
                else:
                    print(Style.BRIGHT + msg + '\n')
            elif msg.startswith('[PM'): 
                print(Fore.YELLOW + Style.BRIGHT + msg + '\n')
            elif msg.startswith('[Sistema]'): 
                print(Fore.MAGENTA + Style.BRIGHT + msg + '\n')
            elif msg.startswith('[ANÚNCIO'): 
                print(Fore.CYAN + Style.BRIGHT + msg + '\n')
            elif msg.startswith('[Votação]'): 
                print(Fore.BLUE + Style.BRIGHT + msg + '\n')
            else:
                print(Fore.GREEN + msg + '\n')

        except ConnectionResetError:
            print(Fore.RED + '\n[Erro] Conexão resetada pelo servidor\n')
            break
        except Exception as e:
            print(Fore.RED + f'\n[Erro ao receber mensagem]: {e}\n')
            break

    stop_threads = True

def sendMessages(client, chave):
    global stop_threads
    while not stop_threads:
        try:
            msg = input('\n')
            if stop_threads:
                break
            if msg.lower() == '/sair':
                print(Fore.CYAN + "[Info] Você saiu da sala.")
                stop_threads = True
                encrypted = encrypt_message("/sair", chave)
                if encrypted:
                    client.send(encrypted)
                break

            if msg.strip():
                encrypted = encrypt_message(msg, chave)
                if encrypted:
                    client.send(encrypted)
                else:
                    print(Fore.RED + "[Erro] Falha ao criptografar mensagem.")

        except EOFError:
            print(Style.BRIGHT + "Input encerrado. Saindo...\n")
            stop_threads = True
            break
        except OSError as e:
            print(Fore.RED + f"\n[Erro de conexão]: {e}\n")
            stop_threads = True
            break
        except Exception as e:
            print(Fore.RED + f"\n[Erro inesperado]: {e}\n")
            stop_threads = True
            break

    try:
        client.close()
    except:
        pass

if __name__ == "__main__":
    main()