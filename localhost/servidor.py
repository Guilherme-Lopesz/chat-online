import threading
import socket
import json
import os
import time
import datetime
#from cryptog import generate_key, encrypt_message, decrypt_message #usar funções de criptografia
from colorama import init, Fore, Style #colocar Cores 


# Inicialização do colorama
init(autoreset=True)


# ========== CONFIGURAÇÕES ==========
LOBBY_FILE = 'lobby.json'
PRIVATE_LOG_FILE = 'private_rooms.log'
SERVER_HOST = 'localhost'
BUFFER_SIZE = 2048
PROTOCOL_TIMEOUT = 10.0


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




# ========== ESTADO GLOBAL ==========
lobby_lock = threading.RLock()
clients = {}
clients_lock = threading.Lock()
mute_list = {}
mute_lock = threading.Lock()

room_state = {
    "vote_in_progress": False, "vote_type": None, "vote_target_user": None,
    "vote_target_socket": None, "votes_for": set(), "votes_against": set(),
    "voters": set()
}
room_state_lock = threading.RLock()




# ========== VALIDAÇÕES ==========
def validate_port(port):
    return 1024 <= port <= 65535

def validate_username(username):
    return (2 <= len(username) <= 20 and 
            not username.startswith('/') and 
            all(c.isalnum() or c in '_- ' for c in username))




# ========== OPERAÇÕES DO LOBBY ==========
def read_lobby(): #Lê a lista de servidores do arquivo do lobby
    with lobby_lock:
        if not os.path.exists(LOBBY_FILE):
            return []
        try:
            with open(LOBBY_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []



def write_lobby(servers):#Escreve a lista de servidores no arquivo do lobby
    with lobby_lock:
        try:
            with open(LOBBY_FILE, 'w') as f:
                json.dump(servers, f, indent=4)
        except IOError as e:
            print(ColorManager.error(f"[Erro] Falha ao escrever no lobby: {e}"))



def add_server_to_lobby(name, port, max_members):#Adiciona um novo servidor ao lobby
    servers = read_lobby()
    if any(s['port'] == port for s in servers):
        print(ColorManager.warning(f"Porta {port} já está listada. Ignorando"))
        return
    
    servers.append({
        "name": name, 
        "port": port, 
        "members": 0, 
        "max": max_members
    })
    write_lobby(servers)



def remove_server_from_lobby(port):#     Remove um servidor do lobby
    with lobby_lock:
        servers = read_lobby()
        new_servers = [s for s in servers if int(s.get('port', 0)) != port]
        write_lobby(new_servers)
    
    print(ColorManager.info(f"Servidor da porta {port} removido do lobby."))



def update_lobby_count(port, delta):# Atualiza o número de membros de um servidor no lobby
    with lobby_lock:
        servers = read_lobby()
        lobby_updated = False
        
        for server in servers:
            if int(server.get('port', 0)) == port:
                current_members = server.get('members', 0)
                if not isinstance(current_members, int): 
                    current_members = 0
                server['members'] = max(0, current_members + delta)
                lobby_updated = True
                break
        
        if lobby_updated:
            write_lobby(servers)



def log_private_room(port, password): # Registra a criação de uma sala privada
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] Private Room Created - Port: {port}, Password: {password}\n"
    
    try:
        with open(PRIVATE_LOG_FILE, 'a') as f:
            f.write(log_entry)
    except Exception as e:
        print(ColorManager.error(f"Falha ao escrever no log privado: {e}"))




# ========== OPERAÇÕES DE CLIENTES ==========
def find_user_by_name(username):
    """Encontra um usuário pelo nome (case-insensitive)"""
    with clients_lock:
        for sock, data in clients.items():
            if data["username"].lower() == username.lower():
                return sock, data
    return None, None



def send_system_message(client_socket, message, CHAVE):
    """Envia uma mensagem do sistema para um cliente específico"""
    try:
        #encrypted_msg = encrypt_message(f"[Sistema] {message}", CHAVE)
        client_socket.send()
    except (OSError, ConnectionError):
        pass  # Cliente desconectado



def kick_user(username, CHAVE, reason="foi expulso"):
    """Expulsa um usuário da sala"""
    socket_to_kick, user_data = find_user_by_name(username)
    if socket_to_kick:
        actual_username = user_data["username"]
        print(ColorManager.info(f"Expulsando {actual_username}..."))
        
        try:
            socket_to_kick.send((f"Você {reason}.", CHAVE))
            socket_to_kick.close()
        except (OSError, ConnectionError):
            pass
    else:
        print(ColorManager.warning(f"Usuário '{username}' não encontrado"))




def mute_user(username, CHAVE, minutes=0):
    """Silencia um usuário por um período determinado"""
    username_lower = username.lower()
    mute_until = float('inf') if minutes <= 0 else time.time() + (minutes * 60)
    
    duration_msg = 'permanentemente' if minutes <= 0 else f'por {minutes} min'
    admin_msg = f"Silenciando {username} {duration_msg}."
    user_msg = f"Você foi silenciado {duration_msg}."

    with mute_lock:
        mute_list[username_lower] = mute_until
    
    print(ColorManager.info(admin_msg))
    
    target_socket, _ = find_user_by_name(username)
    if target_socket:
        send_system_message(target_socket, user_msg, CHAVE)





def unmute_user(username, CHAVE):
    """Remove o silêncio de um usuário"""
    username_lower = username.lower()
    user_was_muted = False
    
    with mute_lock:
        if username_lower in mute_list:
            mute_list.pop(username_lower)
            user_was_muted = True
    
    if user_was_muted:
        print(ColorManager.info(f"Removido silêncio de {username}"))
        target_socket, _ = find_user_by_name(username)
        if target_socket:
            send_system_message(target_socket, "Você não está mais silenciado.", CHAVE)
    else:
        print(ColorManager.warning(f"Usuário '{username}' não estava silenciado"))






def warn_user(username, reason, CHAVE):
    """Envia um aviso formal para um usuário"""
    target_socket, user_data = find_user_by_name(username)
    if target_socket:
        print(ColorManager.info(f"Enviando aviso para {user_data['username']}"))
        msg = f"Você recebeu um AVISO. Motivo: {reason}"
        send_system_message(target_socket, msg, CHAVE)
    else:
        print(ColorManager.warning(f"Usuário '{username}' não encontrado"))




def broadcast_message(message_str, CHAVE, PORTA=-1, skip_client=None):
    """Transmite uma mensagem para todos os clientes conectados"""
    encrypted_msg = (message_str, CHAVE)
    current_clients = {}
    
    with clients_lock:
        current_clients = clients.copy()
    
    for client_socket in current_clients.keys():
        if client_socket != skip_client:
            try:
                client_socket.send(encrypted_msg)
            except (OSError, ConnectionError):
                # Cliente desconectado - remova em uma thread separada
                threading.Thread(
                    target=delete_client, 
                    args=[client_socket, CHAVE, PORTA]
                ).start()





def delete_client(client_socket, CHAVE, PORTA, reason="saiu do chat"):
    """Remove um cliente e limpa seus recursos"""
    username = "Alguém"
    
    with clients_lock:
        user_data = clients.pop(client_socket, None)
        if user_data:
            username = user_data["username"]
    
    with mute_lock:
        if username.lower() in mute_list:
            mute_list.pop(username.lower())
    
    try:
        client_socket.close()
    except (OSError, ConnectionError):
        pass
    
    print(ColorManager.info(f"Conexão perdida com {username}"))
    
    if PORTA != 0:
        update_lobby_count(PORTA, -1)
    
    if CHAVE:
        broadcast_message(f"<{username}> {reason}.", CHAVE, PORTA, None)






# ========== SISTEMA DE VOTAÇÃO ==========
def reset_vote_state():
    """Reseta o estado da votação atual"""
    global room_state
    with room_state_lock:
        room_state = {
            "vote_in_progress": False, "vote_type": None, "vote_target_user": None,
            "vote_target_socket": None, "votes_for": set(), "votes_against": set(),
            "voters": set()
        }




def check_vote_status(CHAVE, PORTA):
    """Verifica e processa o resultado de uma votação em andamento"""
    action_to_take = None
    target_user = None
    vote_type = None
    result_message = ""

    with room_state_lock:
        if not room_state["vote_in_progress"]:
            return

        total_voters = len(room_state["voters"])
        if total_voters < 2:
            result_message = "Votação cancelada: número insuficiente de eleitores"
            reset_vote_state()
        else:
            required_votes = (total_voters // 2) + 1
            votes_for_count = len(room_state["votes_for"])
            votes_against_count = len(room_state["votes_against"])
            total_votes_cast = votes_for_count + votes_against_count

            vote_passed = votes_for_count >= required_votes
            vote_failed = (votes_against_count >= required_votes or 
                          total_votes_cast == total_voters)

            if vote_passed:
                target_user = room_state["vote_target_user"]
                vote_type = room_state["vote_type"]
                result_message = f"A votação foi APROVADA ({votes_for_count} a favor). {target_user} será punido."
                action_to_take = vote_type
                reset_vote_state()
            elif vote_failed:
                result_message = f"A votação FALHOU ({votes_for_count} a favor, {votes_against_count} contra). {room_state['vote_target_user']} não será punido."
                reset_vote_state()

    if result_message:
        broadcast_message(f"[Votação] {result_message}", CHAVE, PORTA)

    if action_to_take == 'kick':
        kick_user(target_user, CHAVE, reason="foi expulso por votação")
    elif action_to_take == 'mute':
        mute_user(target_user, CHAVE, minutes=10)






# ========== HANDLER DE CLIENTES ==========
def accept_connections_loop(server, CHAVE, PASSWORD, PORTA, CHAT_NAME, MAX_MEMBERS):
    """Loop principal para aceitar conexões de clientes"""
    is_public = (PASSWORD is None)
    
    try:
        while True:
            client, addr = server.accept()
            
            with clients_lock:
                if MAX_MEMBERS > 0 and len(clients) >= MAX_MEMBERS:
                    print(ColorManager.warning(f"Conexão recusada de {addr}: Sala cheia."))
                    try:
                        client.send(b"FAIL_FULL")
                    except (OSError, ConnectionError):
                        pass
                    client.close()
                    continue

            print(ColorManager.info(f"Nova tentativa de conexão de: {addr}"))
            
            thread = threading.Thread(
                target=client_handler,
                args=[client, CHAVE, PASSWORD, PORTA, is_public, CHAT_NAME, MAX_MEMBERS]
            )
            thread.start()
            
    except OSError as e:
        if e.errno == 9:  # Bad file descriptor
            print(ColorManager.info("Loop de conexões encerrado (socket fechado)"))
        else:
            print(ColorManager.error(f"Loop de conexões encerrado inesperadamente: {e}"))
    except Exception as e:
        print(ColorManager.error(f"Erro inesperado no loop de conexões: {e}"))






def process_regular_message(username, msg, CHAVE, client, PORTA):
    """Processa mensagens regulares (não-comando) com proteção contra spam"""
    now = time.time()
    
    with clients_lock:
        if client not in clients:
            return
        user_data = clients[client]

    # Sistema anti-spam
    if now - user_data["last_msg_time"] < 5.0:
        user_data["msg_count"] += 1
    else:
        user_data["msg_count"] = 1
    
    user_data["last_msg_time"] = now

    if user_data["msg_count"] > 10:
        user_data["infractions"] += 1
        user_data["msg_count"] = 0
        
        if user_data["infractions"] == 1:
            warn_user(username, "Spam (Aviso 1/3)", CHAVE)
        elif user_data["infractions"] == 2:
            send_system_message(client, "Spam (Aviso 2/3). Você foi silenciado por 5 minutos", CHAVE)
            mute_user(username, CHAVE, minutes=5)
        elif user_data["infractions"] >= 3:
            kick_user(username, CHAVE, reason="foi expulso por spam excessivo (3 avisos)")
            return

    # Transmissão da mensagem normal
    full_message = f"<{username}> {msg}"
    broadcast_message(full_message, CHAVE, PORTA, client)






def handle_private_message(username, msg, CHAVE, client):
    """Processa mensagens privadas"""
    parts = msg.split(' ', 2)
    if len(parts) < 3:
        send_system_message(client, "Uso: /pm <username> <mensagem>", CHAVE)
        return

    target_username = parts[1]
    pm_text = parts[2]
    target_socket, target_data = find_user_by_name(target_username)
    
    if target_socket:
        if target_socket == client:
            send_system_message(client, "Não pode enviar PM para si mesmo", CHAVE)
        elif target_data["pm_blocked"]:
            send_system_message(client, f"'{target_data['username']}' não aceita PMs", CHAVE)
        else:
            pm_to_target = f"[PM de {username}] {pm_text}"
            target_socket.send((pm_to_target, CHAVE))
            pm_confirm = f"[PM enviada para {target_data['username']}] {pm_text}"
            client.send((pm_confirm, CHAVE))
    else:
        send_system_message(client, f"Usuário '{target_username}' não encontrado", CHAVE)






def handle_vote_start(username, msg, CHAVE, PORTA, client):
    """Inicia uma votação"""
    with room_state_lock:
        if room_state["vote_in_progress"]:
            send_system_message(client, "Já existe uma votação em progresso", CHAVE)
            return

        vote_type = 'kick' if 'votekick' in msg.lower() else 'mute'
        target_username = msg.split(' ', 1)[1]
        target_socket, target_data = find_user_by_name(target_username)

        if not target_socket:
            send_system_message(client, f"Usuário '{target_username}' não encontrado", CHAVE)
        elif target_socket == client:
            send_system_message(client, "Não pode iniciar votação contra si mesmo", CHAVE)
        else:
            with clients_lock:
                current_usernames = set(data["username"] for data in clients.values())
            
            if len(current_usernames) < 2:
                send_system_message(client, "São necessários pelo menos 2 usuários para votar", CHAVE)
                return

            room_state["vote_in_progress"] = True
            room_state["vote_type"] = vote_type
            room_state["vote_target_user"] = target_data["username"]
            room_state["vote_target_socket"] = target_socket
            room_state["voters"] = current_usernames
            room_state["votes_for"] = {username}
            room_state["votes_against"] = set()

            broadcast_message(f"[Votação] {username} iniciou votação para {vote_type} {target_data['username']}", CHAVE, PORTA)
            broadcast_message(f"[Votação] Digite /vote yes ou /vote no", CHAVE, PORTA)
            check_vote_status(CHAVE, PORTA)







def handle_vote_cast(username, msg_lower, CHAVE, PORTA, client):
    """Processa um voto em uma eleição"""
    with room_state_lock:
        if not room_state["vote_in_progress"]:
            send_system_message(client, "Nenhuma votação em progresso", CHAVE)
        elif username not in room_state["voters"]:
            send_system_message(client, "Não pode votar (não estava online no início)", CHAVE)
        elif username in room_state["votes_for"] or username in room_state["votes_against"]:
            send_system_message(client, "Você já votou", CHAVE)
        else:
            vote = 'SIM'
            if 'yes' in msg_lower:
                room_state["votes_for"].add(username)
            else:
                room_state["votes_against"].add(username)
                vote = 'NÃO'
            
            broadcast_message(f"[Votação] {username} votou {vote}.", CHAVE, PORTA)
            check_vote_status(CHAVE, PORTA)







def process_command(username, msg, CHAVE, PORTA, CHAT_NAME, MAX_MEMBERS, client):
    """Processa comandos do usuário"""
    msg_lower = msg.lower()
    
    if msg_lower == '/help':
        help_text = "Comandos: /sair, /users, /info, /pm <user> <msg>, /togglepm, /votekick <user>, /votemute <user>, /vote <yes/no>"
        send_system_message(client, help_text, CHAVE)

    elif msg_lower == '/togglepm':
        with clients_lock:
            if client not in clients:
                return
            clients[client]["pm_blocked"] = not clients[client]["pm_blocked"]
            status = "BLOQUEADAS" if clients[client]["pm_blocked"] else "DESBLOQUEADAS"
        send_system_message(client, f"Mensagens privadas agora estão {status}.", CHAVE)

    elif msg_lower.startswith('/pm '):
        handle_private_message(username, msg, CHAVE, client)

    elif msg_lower == '/info':
        max_members_display = 'N/A' if MAX_MEMBERS == float('inf') else str(MAX_MEMBERS)
        with clients_lock:
            num_clients = len(clients)
        info = f"Sala: '{CHAT_NAME}', Membros: {num_clients}/{max_members_display}"
        send_system_message(client, info, CHAVE)

    elif msg_lower.startswith('/votekick ') or msg_lower.startswith('/votemute '):
        handle_vote_start(username, msg, CHAVE, PORTA, client)

    elif msg_lower == '/vote yes' or msg_lower == '/vote no':
        handle_vote_cast(username, msg_lower, CHAVE, PORTA, client)

    elif msg_lower == '/users':
        with clients_lock:
            user_list = ", ".join([data["username"] for data in clients.values()])
        response = f"[Sistema] Usuários online ({len(clients)}): {user_list}"
        client.send((response, CHAVE))

    else:
        # Mensagem normal
        full_message = f"<{username}> {msg}"
        broadcast_message(full_message, CHAVE, PORTA, client)






def client_handler(client, CHAVE, PASSWORD, PORTA, is_public, CHAT_NAME, MAX_MEMBERS):
    """Gerencia a comunicação com um cliente específico"""
    username = ""
    username_lower = ""
    
    try:
        # Autenticação por senha (se aplicável)
        if PASSWORD is not None:
            password_attempt = client.recv(1024).decode('utf-8')
            if password_attempt != PASSWORD:
                print(ColorManager.warning("Tentativa de conexão falhou: Senha errada"))
                client.send(b"FAIL     ")
                client.close()
                return

        # Envio da chave de criptografia
        client.send(CHAVE)

        # Recebimento e validação do nome de usuário
        encrypted_username = client.recv(BUFFER_SIZE)
        username = (encrypted_username, CHAVE).strip()
        username_lower = username.lower()

        # Validação do nome de usuário
        if not validate_username(username):
            print(ColorManager.warning(f"Nome de usuário inválido: {username}"))
            client.send(b"FAIL_NAME")
            client.close()
            return

        # Verificação de nome duplicado
        with clients_lock:
            for data in clients.values():
                if data["username"].lower() == username_lower:
                    print(ColorManager.warning(f"Conexão recusada: Nome '{username}' já em uso"))
                    client.send(b"FAIL_NAME")
                    client.close()
                    return

        client.send(b"OK_NAME  ")

        # Registro do cliente
        with clients_lock:
            clients[client] = {
                "username": username,
                "pm_blocked": False,
                "last_msg_time": time.time(),
                "msg_count": 0,
                "infractions": 0
            }

        print(ColorManager.success(f"'{username}' entrou no chat"))
        
        if is_public:
            update_lobby_count(PORTA, +1)

        broadcast_message(f"<{username}> entrou no chat", CHAVE, PORTA, client)

        # Mensagem de boas-vindas
        max_members_display = 'N/A' if MAX_MEMBERS == float('inf') else str(MAX_MEMBERS)
        welcome_msg = f"Você entrou no chat '{CHAT_NAME}'. {len(clients)}/{max_members_display} usuários online."
        send_system_message(client, welcome_msg, CHAVE)




        # Verificação de mute status
        with mute_lock:
            mute_until = mute_list.get(username_lower)
        
        if mute_until:
            now = time.time()
            if now < mute_until:
                if mute_until == float('inf'):
                    msg = "Você está silenciado permanentemente nesta sala"
                else:
                    remaining = int(mute_until - now)
                    msg = f"Você continua silenciado. Faltam {remaining // 60}m {remaining % 60}s"
                send_system_message(client, msg, CHAVE)
            else:
                with mute_lock:
                    mute_list.pop(username_lower, None)

    except Exception as e:
        print(ColorManager.error(f"Erro na autenticação: {e}"))
        client.close()
        return




    # Loop principal de mensagens do cliente
    while True:
        try:
            msg_criptografada = client.recv(BUFFER_SIZE)
            if not msg_criptografada:
                break

            msg = (msg_criptografada, CHAVE).strip()

            # Verificação de mute
            with mute_lock:
                mute_until = mute_list.get(username_lower)
            
            if mute_until:
                now = time.time()
                if now < mute_until:
                    if mute_until == float('inf'):
                        msg_mute = "Você está silenciado permanentemente"
                    else:
                        remaining = int(mute_until - now)
                        msg_mute = f"Você está silenciado. Faltam {remaining // 60}m {remaining % 60}s"
                    send_system_message(client, msg_mute, CHAVE)
                    continue
                else:
                    unmute_user(username, CHAVE)

            # Processamento de comandos e mensagens
            if not msg.startswith('/'):
                process_regular_message(username, msg, CHAVE, client, PORTA)
            else:
                process_command(username, msg, CHAVE, PORTA, CHAT_NAME, MAX_MEMBERS, client)

        except ConnectionResetError:
            print(ColorManager.info(f"Conexão resetada por {username}"))
            break
        except Exception as e:
            print(ColorManager.error(f"Erro no loop do cliente {username}: {e}"))
            break

    delete_client(client, CHAVE, PORTA)






# ========== INTERFACE ADMINISTRATIVA ==========
def handle_admin_command(cmd, CHAVE_SECRETA, PORTA, is_public):
    """Processa comandos do administrador"""
    cmd_parts = cmd.split()
    if not cmd_parts:
        return True  # Continuar loop

    command = cmd_parts[0].lower()

    command_handlers = {
        'sair': lambda: admin_command_sair(PORTA, is_public),
        'users': lambda: admin_command_users(),
        'kick': lambda: admin_command_kick(cmd_parts, CHAVE_SECRETA),
        'warn': lambda: admin_command_warn(cmd_parts, CHAVE_SECRETA),
        'mute': lambda: admin_command_mute(cmd_parts, CHAVE_SECRETA),
        'unmute': lambda: admin_command_unmute(cmd_parts, CHAVE_SECRETA),
        'broadcast': lambda: admin_command_broadcast(cmd, CHAVE_SECRETA, PORTA)
    }

    handler = command_handlers.get(command)
    if handler:
        return handler()
    else:
        print(ColorManager.warning(f"Comando desconhecido: '{cmd}'"))
        return True





def admin_command_sair(PORTA, is_public):
    """Comando sair do administrador"""
    print(ColorManager.info("Comando 'sair' recebido. Desligando esta sala..."))
    if is_public:
        remove_server_from_lobby(PORTA)
    return False




def admin_command_users():
    """Lista usuários online"""
    with clients_lock:
        if not clients:
            print(ColorManager.info("Nenhum usuário online"))
        else:
            user_list = ", ".join([data["username"] for data in clients.values()])
            print(ColorManager.info(f"Usuários online ({len(clients)}): {user_list}"))
    return True





def admin_command_kick(cmd_parts, CHAVE_SECRETA):
    """Expulsa um usuário"""
    if len(cmd_parts) < 2:
        print(ColorManager.warning("Uso: kick <username>"))
    else:
        kick_user(cmd_parts[1], CHAVE_SECRETA, reason="foi expulso pelo anfitrião")
    return True





def admin_command_warn(cmd_parts, CHAVE_SECRETA):
    """Adverte um usuário"""
    if len(cmd_parts) < 2:
        print(ColorManager.warning("Uso: warn <username>"))
    else:
        warn_user(cmd_parts[1], "Comportamento inadequado (aviso do admin)", CHAVE_SECRETA)
    return True






def admin_command_mute(cmd_parts, CHAVE_SECRETA):
    """Silencia um usuário"""
    if len(cmd_parts) < 2:
        print(ColorManager.warning("Uso: mute <username> [minutos]"))
    else:
        minutes = 0
        if len(cmd_parts) > 2 and cmd_parts[2].isdigit():
            minutes = int(cmd_parts[2])
        mute_user(cmd_parts[1], CHAVE_SECRETA, minutes)
    return True






def admin_command_unmute(cmd_parts, CHAVE_SECRETA):
    """Remove silêncio de um usuário"""
    if len(cmd_parts) < 2:
        print(ColorManager.warning("Uso: unmute <username>"))
    else:
        unmute_user(cmd_parts[1], CHAVE_SECRETA)
    return True





def admin_command_broadcast(cmd, CHAVE_SECRETA, PORTA):
    """Transmite uma mensagem para todos"""
    if len(cmd.split()) < 2:
        print(ColorManager.warning("Uso: broadcast <mensagem>"))
    else:
        message = cmd.split(' ', 1)[1]
        print(ColorManager.info("Enviando anúncio..."))
        anuncio = f"[ANÚNCIO DO ADMIN] {message}"
        broadcast_message(anuncio, CHAVE_SECRETA, PORTA)
    return True






# ========== FUNÇÃO PRINCIPAL ==========
def main():
    """Função principal do servidor"""
    while True:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        CHAVE_SECRETA =()
        
        # Limpeza de estado global
        clients.clear()
        mute_list.clear()
        reset_vote_state()

        print(ColorManager.success("\n--- Criar Novo Chat (Menu Principal) ---"))

        # Configuração inicial da sala
        SENHA, chat_name, is_public = setup_chat_type()
        if not chat_name:
            continue

        PORTA = setup_port()
        if not PORTA:
            continue

        MAX_MEMBERS = setup_member_limit()
        if MAX_MEMBERS is None:
            continue

        # Inicialização do servidor
        if not initialize_server(server, PORTA):
            continue

        # Registro da sala
        max_members_display = 'N/A' if MAX_MEMBERS == 0 else str(MAX_MEMBERS)
        if is_public:
            add_server_to_lobby(chat_name, PORTA, max_members_display)
            print(ColorManager.success(f"Sala Pública {chat_name} registrada na PORTA:{PORTA} (Max: {max_members_display})"))
        else:
            log_private_room(PORTA, SENHA)
            print(ColorManager.success(f"Sala Privada criada na PORTA: {PORTA} (Max: {max_members_display})"))
            print(ColorManager.info(f"SENHA: {SENHA}"))

        print("---------------------------------------")
        print(ColorManager.info(f"Aguardando conexões na porta {PORTA}..."))

        # Início do loop de aceitação de conexões
        accept_thread = threading.Thread(
            target=accept_connections_loop,
            args=[server, CHAVE_SECRETA, SENHA, PORTA, chat_name, MAX_MEMBERS if MAX_MEMBERS > 0 else float('inf')]
        )
        accept_thread.daemon = True
        accept_thread.start()

        print(ColorManager.success("Servidor rodando. O terminal está livre"))
        print(ColorManager.info("Comandos: 'users', 'kick <user>', 'warn <user>', 'mute <user> [min]', 'unmute <user>', 'broadcast <msg>', 'sair'"))

        # Loop de comandos do administrador
        try:
            running = True
            while running:
                cmd = input().strip()
                running = handle_admin_command(cmd, CHAVE_SECRETA, PORTA, is_public)

        except KeyboardInterrupt:
            print(ColorManager.info("\nCtrl+C recebido. Desligando esta sala..."))
            if is_public:
                remove_server_from_lobby(PORTA)

        # Limpeza final
        print(ColorManager.info("Fechando servidor e conexões..."))
        server.close()
        
        with clients_lock:
            for client_socket in list(clients.keys()):
                client_socket.close()
            clients.clear()
        
        with mute_lock:
            mute_list.clear()
        
        reset_vote_state()
        print(ColorManager.info("Sala desligada. Voltando ao menu principal..."))







def setup_chat_type():
    """Configura o tipo de chat (público/privado)"""
    while True:
        choice = input("\n1: Criar Chat Público \n2: Criar Chat Privado \nEscolha: ")
        
        if choice == '1':
            chat_name = input("\nDigite um nome público para sua sala: ")
            return None, chat_name, True
        elif choice == '2':
            SENHA = input("\nDigite uma SENHA para sua sala: ")
            return SENHA, "Chat Privado", False
        else:
            print(ColorManager.error("Opção inválida"))






def setup_port():
    """Configura e valida a porta do servidor"""
    while True:
        try:
            port = int(input("Digite a PORTA para o seu novo chat (ex: 50001): "))
            if validate_port(port):
                return port
            else:
                print(ColorManager.error("Porta deve estar entre 1024 e 65535"))
        except ValueError:
            print(ColorManager.error("Isso não é um número válido"))






def setup_member_limit():
    """Configura o limite de membros"""
    while True:
        try:
            limit_str = input("Limite de membros (0 para ilimitado): ")
            limit = int(limit_str)
            
            if limit < 0:
                print(ColorManager.error("O limite não pode ser negativo"))
            elif limit == 1:
                print(ColorManager.error("O limite mínimo é 2 (ou 0 para ilimitado)"))
            else:
                return limit
        except ValueError:
            print(ColorManager.error("Isso não é um número válido"))






def initialize_server(server, port):
    """Inicializa o socket do servidor"""
    try:
        server.bind((SERVER_HOST, port))
        server.listen()
        return True
    except OSError as e:
        print(ColorManager.error(f"Erro: Porta {port} já está em uso. {e}"))
        print(ColorManager.info("Voltando ao menu principal..."))
        return False

if __name__ == "__main__":
    main()