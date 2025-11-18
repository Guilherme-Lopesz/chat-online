import threading
import socket
import json
import os
import sys
from cryptog import encrypt_message, decrypt_message
from colorama import init, Fore, Style


# Inicialização do colorama
init(autoreset=True)


# ========== CONFIGURAÇÕES ==========
LOBBY_FILE = 'lobby.json'
SERVER_HOST = 'localhost'
BUFFER_SIZE = 2048
PROTOCOL_TIMEOUT = 10.0
SOCKET_TIMEOUT = 5.0



# ========== GERENCIADOR DE CORES ========== (Padronização das cores usadas no terminal)
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
    
    @staticmethod
    def announcement(msg):
        return Fore.CYAN + Style.BRIGHT + msg
    
    @staticmethod
    def private_msg(msg):
        return Fore.YELLOW + Style.BRIGHT + msg
    
    @staticmethod
    def vote(msg):
        return Fore.BLUE + Style.BRIGHT + msg
    
    @staticmethod
    def user_msg(msg):
        return Fore.WHITE + Style.BRIGHT + msg

# ========== OPERAÇÕES DO LOBBY ==========
def read_lobby():
    """Lê e retorna a lista de servidores do lobby"""
    try:
        if not os.path.exists(LOBBY_FILE):
            return []
        with open(LOBBY_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []



# ========== VALIDAÇÕES ==========
def validate_port(port): #    Valida se a porta está no intervalo correto
    return 1024 <= port <= 65535



def validate_username(username): #      Valida o nome de usuário (2-20 chars, sem '/')
    return (2 <= len(username) <= 20 and 
            not username.startswith('/') and 
            all(c.isalnum() or c in '_- ' for c in username))



# ========== MENU DE AJUDA ==========
def print_help_menu(): #    Exibe o menu de ajuda completo
    print(ColorManager.info("\n--- Central de Ajuda ---"))
    
    print(Style.BRIGHT + "\nEste programa permite que você entre em chats.")
    
    print(Style.BRIGHT + "\nComandos disponíveis DENTRO de um chat:")
    commands = [
        ("/help", "Mostra esta ajuda dentro do chat."),
        ("/sair", "Desconecta você do chat atual e retorna ao menu principal."),
        ("/users", "Lista todos os usuários atualmente online na mesma sala."),
        ("/info", "Mostra o nome da sala, nº de membros e limite."),
        ("/pm <user> <msg>", "Envia uma mensagem privada para um usuário."),
        ("/togglepm", "Bloqueia ou desbloqueia o recebimento de PMs."),
        ("/votekick <user>", "Inicia uma votação para expulsar um usuário."),
        ("/votemute <user>", "Inicia uma votação para silenciar um usuário (10 min)."),
        ("/vote <yes/no>", "Vota numa eleição em progresso.")
    ]
    
    for cmd, desc in commands:
        print(Fore.GREEN + f"  {cmd:<15}" + Style.RESET_ALL + f"- {desc}")
    
    print(Style.BRIGHT + "\nPara Anfitriões (rodando 'servidor.py'):")
    admin_commands = [
        ("users", "Lista os usuários conectados na sua sala."),
        ("kick <user>", "Expulsa um usuário da sua sala."),
        ("warn <user>", "Envia um aviso formal para um usuário."),
        ("mute <user> [min]", "Silencia um usuário (permanentemente ou por [min] minutos)."),
        ("unmute <user>", "Remove o silêncio de um usuário."),
        ("broadcast <msg>", "Envia um anúncio global para todos na sala."),
        ("sair", "Desliga a sala atual e volta ao menu de criação.")
    ]
    
    for cmd, desc in admin_commands:
        print(Fore.YELLOW + f"    {cmd:<18}" + Style.RESET_ALL + f"- {desc}")
    
    print(Style.BRIGHT + "\nLimitações:")
    print(" - Chats públicos não precisam de senha, mas chats privados sim.")
    print(" - Um log de salas privadas (porta e senha) é salvo em 'private_rooms.log'.")
    print(" - O Anti-Flood automático bane após 3 infrações (Aviso -> Mute 5 min -> Expulsão).")
    
    print(ColorManager.info("------------------------"))
    input(Style.DIM + "\nPressione <Enter> para voltar ao menu...")








# ========== MENU PRINCIPAL ==========
def main():
    """Função principal do cliente"""
    while True:
        display_main_menu()
        choice = input("Escolha: ").strip()
        
        if choice == '1':
            porta = handle_public_chat_selection()
            if porta:
                connect_to_chat(porta, None)
        elif choice == '2':
            porta, senha = handle_private_chat_selection()
            if porta:
                connect_to_chat(porta, senha)
        elif choice == '3':
            print_help_menu()
        elif choice == '4':
            print(ColorManager.success("\nSaindo do programa. Até logo!"))
            sys.exit()
        else:
            print(ColorManager.error("Opção inválida"))




def display_main_menu():
    """Exibe o menu principal"""
    print(Style.BRIGHT + Fore.GREEN + "\n--- Bem-vindo ao Chat (Terminal) ---")
    print("1: Entrar em um Chat Público")
    print("2: Entrar em um Chat Privado")
    print("3: Ajuda")
    print("4: Sair do Programa")





def handle_public_chat_selection():
    """Manipula a seleção de chat público"""
    servers = read_lobby()
    if not servers:
        print(ColorManager.warning("\nNenhum chat público encontrado"))
        return None
    
    display_public_chats(servers)
    return select_chat_from_list(servers)




def handle_private_chat_selection():
    """Manipula a seleção de chat privado"""
    try:
        porta = int(input("\nDigite a PORTA do chat privado: "))
        if not validate_port(porta):
            print(ColorManager.error("Porta deve estar entre 1024 e 65535"))
            return None, None
        
        senha = input("Digite a SENHA do chat: ")
        return porta, senha
    except ValueError:
        print(ColorManager.error("A porta deve ser um número"))
        return None, None




def display_public_chats(servers):
    """Exibe a lista de chats públicos disponíveis"""
    print(Style.BRIGHT + "\n--- Chats Públicos Ativos ---")
    for i, server in enumerate(servers):
        members = server.get('members', 0)
        max_members = server.get('max', 'N/A')
        name = server.get('name', 'Sala Sem Nome')
        port = server.get('port', 'N/A')
        
        print(f"{i+1}: {name} ({members}/{max_members}) - Porta: {port}")




def select_chat_from_list(servers):
    """Seleciona um chat da lista"""
    try:
        select_num = int(input("\nDigite o número do chat para entrar: "))
        if 1 <= select_num <= len(servers):
            selected_server = servers[select_num - 1]
            porta = int(selected_server['port'])
            print(ColorManager.info(f"Conectando à sala '{selected_server['name']}'..."))
            return porta
        else:
            print(ColorManager.error("Número inválido"))
            return None
    except (ValueError, IndexError):
        print(ColorManager.error("Entrada inválida ou erro ao ler lobby"))
        return None





# ========== CONEXÃO E AUTENTICAÇÃO ==========
def connect_to_chat(porta, senha):
    """Estabelece conexão com o chat e gerencia a sessão"""
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(PROTOCOL_TIMEOUT)
    
    try:
        client.connect((SERVER_HOST, porta))
        client.settimeout(None)
        
        # Autenticação
        if not authenticate_client(client, senha):
            client.close()
            return
        
        # Recebimento da chave
        chave_bytes = receive_encryption_key(client)
        if not chave_bytes:
            client.close()
            return
        
        # Autenticação do usuário
        if not authenticate_username(client, chave_bytes):
            client.close()
            return
        
        # Início da sessão de chat
        start_chat_session(client, chave_bytes)
        
    except ConnectionRefusedError:
        print(ColorManager.error(f"\nNinguém está ouvindo na porta {porta}"))
    except socket.timeout:
        print(ColorManager.error(f"\nTempo limite de conexão excedido para a porta {porta}"))
        safe_close_socket(client)
    except Exception as e:
        print(ColorManager.error(f"\nNão foi possível estabelecer conexão: {e}"))
        safe_close_socket(client)




def authenticate_client(client, senha):
    """Autentica o cliente com senha (se necessário)"""
    if senha is not None:
        client.send(senha.encode('utf-8'))
        initial_response = client.recv(9)
        
        if initial_response == b"FAIL     ":
            print(ColorManager.error("\nSenha incorreta. Conexão recusada"))
            return False
        elif initial_response == b"FAIL_FULL":
            print(ColorManager.error("\nA sala está cheia"))
            return False
    
    return True





def receive_encryption_key(client):
    """Recebe a chave de criptografia do servidor"""
    try:
        initial_response = client.recv(9)
        
        if initial_response in [b"FAIL     ", b"FAIL_FULL"]:
            handle_protocol_errors(initial_response)
            return None
        
        # A chave Fernet tem 44 bytes
        remaining_bytes = 44 - len(initial_response)
        if remaining_bytes < 0:
            print(ColorManager.error("Resposta inesperada do servidor ao receber chave"))
            return None
        
        if remaining_bytes > 0:
            client.settimeout(SOCKET_TIMEOUT)
            key_bytes_remaining = client.recv(remaining_bytes)
            client.settimeout(None)
            chave_bytes = initial_response + key_bytes_remaining
        else:
            chave_bytes = initial_response
        
        if len(chave_bytes) != 44:
            print(ColorManager.error(f"Falha ao receber a chave completa. Esperava 44 bytes, recebeu {len(chave_bytes)}"))
            return None
        
        return chave_bytes
        
    except socket.timeout:
        print(ColorManager.error("Tempo limite ao receber chave do servidor"))
        return None





def authenticate_username(client, chave_bytes):
    """Autentica o nome de usuário com o servidor"""
    username = input('Usuário> ').strip()
    
    if not validate_username(username):
        print(ColorManager.error("Nome de usuário inválido. Use apenas letras, números e '-_' (2-20 caracteres)"))
        return False
    
    try:
        client.send(encrypt_message(username, chave_bytes))
        client.settimeout(SOCKET_TIMEOUT)
        auth_status = client.recv(9)
        client.settimeout(None)
        
        if auth_status == b"FAIL_NAME":
            print(ColorManager.error(f"O nome '{username}' já está em uso nesta sala"))
            return False
        elif auth_status != b"OK_NAME  ":
            print(ColorManager.error("Resposta inesperada do servidor após enviar nome"))
            return False
        
        return True
        
    except socket.timeout:
        print(ColorManager.error("Tempo limite de autenticação excedido"))
        return False





def handle_protocol_errors(response):
    """Manipula erros de protocolo do servidor"""
    if response == b"FAIL     ":
        print(ColorManager.error("Senha incorreta. Conexão recusada"))
    elif response == b"FAIL_FULL":
        print(ColorManager.error("A sala está cheia"))





def safe_close_socket(sock):
    """Fecha um socket de forma segura"""
    try:
        sock.close()
    except:
        pass




# ========== SESSÃO DE CHAT ==========
def start_chat_session(client, chave_bytes):
    """Inicia a sessão de chat com threads de envio e recebimento"""
    global stop_threads
    stop_threads = False
    
    print(ColorManager.success("\n--- Conectado ao Chat ---"))
    print("Digite '/help' para ver os comandos")
    
    # Iniciar threads
    receive_thread = threading.Thread(target=receiveMessages, args=[client, chave_bytes])
    send_thread = threading.Thread(target=sendMessages, args=[client, chave_bytes])
    
    receive_thread.start()
    send_thread.start()
    
    # Aguardar término das threads
    receive_thread.join()
    send_thread.join()
    
    print(Style.BRIGHT + "\nDesconectado. Voltando ao menu principal...")





def receiveMessages(client, chave):
    """Thread para recebimento de mensagens"""
    global stop_threads
    
    while not stop_threads:
        try:
            msg_criptografada = client.recv(BUFFER_SIZE)
            if not msg_criptografada:
                if not stop_threads:
                    print(ColorManager.warning('\nO servidor fechou a sala'))
                    stop_threads = True
                break
            
            msg = decrypt_message(msg_criptografada, chave)
            display_formatted_message(msg)

        except ConnectionResetError:
            if not stop_threads:
                print(ColorManager.error('\nA conexão foi resetada pelo servidor'))
            break
        except Exception as e:
            if not stop_threads:
                print(ColorManager.error(f'\nErro ao receber mensagem: {e}'))
            break
    
    stop_threads = True






def display_formatted_message(msg):
    """Exibe mensagens formatadas com cores apropriadas"""
    if msg.startswith('<'):
        parts = msg.split('>', 1)
        if len(parts) == 2:
            print(ColorManager.user_msg(parts[0] + '>') + Style.NORMAL + parts[1])
        else:
            print(Style.BRIGHT + msg)
    elif msg.startswith('[PM'):
        print(ColorManager.private_msg(msg))
    elif msg.startswith('[Sistema]'):
        print(ColorManager.system(msg))
    elif msg.startswith('[ANÚNCIO'):
        print(ColorManager.announcement(msg))
    elif msg.startswith('[Votação]'):
        print(ColorManager.vote(msg))
    else:
        print(ColorManager.info(msg))




def sendMessages(client, chave):
    """Thread para envio de mensagens"""
    global stop_threads
    
    while not stop_threads:
        try:
            msg = input()
            if stop_threads:
                break
            
            if msg.lower() == '/sair':
                handle_exit_command(client, chave)
                break
            
            if msg.strip():
                client.send(encrypt_message(msg, chave))
                
        except EOFError:
            print(Style.BRIGHT + "Input interrompido. Saindo...")
            stop_threads = True
            break
        except OSError as e:
            if not stop_threads:
                print(ColorManager.error(f"Erro de conexão ao enviar: {e}"))
            stop_threads = True
            break
        except Exception as e:
            if not stop_threads:
                print(ColorManager.error(f"Erro inesperado ao enviar mensagem: {e}"))
            stop_threads = True
            break
    
    safe_close_socket(client)



def handle_exit_command(client, chave):
    """Manipula o comando de saída do usuário"""
    print(Style.BRIGHT + "Saindo do chat...")
    global stop_threads
    stop_threads = True
    try:
        client.send(encrypt_message("/sair", chave))
    except:
        pass

# Variável para controle das threads
stop_threads = False

if __name__ == "__main__":
    main()