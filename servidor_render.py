import threading
import socket
import json
import os
import time
from cryptog import generate_key, encrypt_message, decrypt_message
from colorama import init, Fore, Style

init(autoreset=True)

# 🔥 CONFIGURAÇÃO AUTOMÁTICA PARA RENDER
PORT = int(os.environ.get('PORT', 50001))
HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'chat-online-vj6d.onrender.com')
CHAT_NAME = "🎪 Chat Online Render"
PASSWORD = None
MAX_MEMBERS = 0  # Ilimitado

print(Fore.GREEN + "\n" + "="*50)
print("🚀 SERVIDOR RENDER - INICIALIZAÇÃO AUTOMÁTICA")
print("="*50)
print(Fore.CYAN + f"🏷️  Nome: {CHAT_NAME}")
print(Fore.CYAN + f"🌐 URL: https://{HOSTNAME}")
print(Fore.CYAN + f"🎯 Porta: {PORT}")
print(Fore.CYAN + f"👥 Limite: Ilimitado")
print(Fore.CYAN + f"📢 Tipo: Público")
print("="*50)

# Variáveis globais
LOBBY_FILE = 'lobby.json'
PRIVATE_LOG_FILE = 'private_rooms.log'
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

# Funções de lobby
def read_lobby():
    with lobby_lock:
        if not os.path.exists(LOBBY_FILE):
            return []
        try:
            with open(LOBBY_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []

def write_lobby(servers):
    with lobby_lock:
        with open(LOBBY_FILE, 'w') as f:
            json.dump(servers, f, indent=4)

def add_server_to_lobby(name, port, max_members):
    servers = read_lobby()
    if any(s['port'] == port for s in servers):
        print(f"A porta {port} já está listada. Ignorando")
        return
    servers.append({"name": name, "port": port, "members": 0, "max": max_members})
    write_lobby(servers)

def remove_server_from_lobby(port):
    with lobby_lock:
        servers = read_lobby()
        new_servers = [s for s in servers if int(s.get('port', 0)) != port]
        write_lobby(new_servers)
    if os.path.exists(LOBBY_FILE):
        print(f"\n[Info] Servidor da porta {port} removido do lobby.")

def update_lobby_count(port, delta):
    with lobby_lock:
        servers = read_lobby()
        lobby_updated = False
        for server in servers:
            if int(server.get('port', 0)) == port:
                current_members = server.get('members', 0)
                if not isinstance(current_members, int): current_members = 0
                server['members'] = max(0, current_members + delta)
                lobby_updated = True
                break
        if lobby_updated:
            write_lobby(servers)

def log_private_room(port, password):
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] Private Room Created - Port: {port}, Password: {password}\n"
    try:
        with open(PRIVATE_LOG_FILE, 'a') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"[Admin Error] Falha ao escrever no log privado: {e}")

# Funções do servidor
def accept_connections_loop(server, CHAVE, PASSWORD, PORTA, CHAT_NAME, MAX_MEMBERS):
    is_public = (PASSWORD is None)
    try:
        while True:
            client, addr = server.accept()
            with clients_lock:
                if MAX_MEMBERS > 0 and len(clients) >= MAX_MEMBERS:
                    print(f"[Info] Conexão recusada de {addr}: Sala cheia.")
                    try: client.send(b"FAIL_FULL")
                    except: pass
                    client.close()
                    continue
            print(f'[Info] Nova conexão de: {addr}')
            thread = threading.Thread(
                target=client_handler,
                args=[client, CHAVE, PASSWORD, PORTA, is_public, CHAT_NAME, MAX_MEMBERS]
            )
            thread.start()
    except Exception as e:
        if isinstance(e, OSError) and e.errno == 9:
             print(f"[Info] Conexões encerradas (socket fechado)")
        else:
             print(f"[Info] Conexões encerradas: {e}")

def find_user_by_name(username):
    with clients_lock:
        for sock, data in clients.items():
            if data["username"].lower() == username.lower():
                return sock, data
    return None, None

def send_system_message(client_socket, message, CHAVE):
    encrypted = encrypt_message(f"[Sistema] {message}", CHAVE)
    if encrypted:
        try: client_socket.send(encrypted)
        except: pass

def kick_user(username, CHAVE, reason="foi expulso"):
    socket_to_kick, user_data = find_user_by_name(username)
    if socket_to_kick:
        actual_username = user_data["username"]
        print(f"[Admin] Expulsando {actual_username}...")
        encrypted = encrypt_message(f"Você {reason}.", CHAVE)
        if encrypted:
            try: socket_to_kick.send(encrypted)
            except: pass
        try: socket_to_kick.close()
        except: pass
    else: print(f"[Admin] Usuário '{username}' não encontrado")

def mute_user(username, CHAVE, minutes=0):
    username_lower = username.lower()
    mute_until = float('inf') if minutes <= 0 else time.time() + (minutes * 60)
    msg_admin = f"[Admin] Silenciando {username} {'permanentemente' if minutes <= 0 else f'por {minutes} min'}."
    msg_user = f"Você foi silenciado {'permanentemente' if minutes <= 0 else f'por {minutes} minutos'}."
    with mute_lock: mute_list[username_lower] = mute_until
    print(msg_admin)
    target_socket, _ = find_user_by_name(username)
    if target_socket: send_system_message(target_socket, msg_user, CHAVE)

def unmute_user(username, CHAVE):
    username_lower = username.lower()
    user_was_muted = False
    with mute_lock:
        if username_lower in mute_list:
            mute_list.pop(username_lower); user_was_muted = True
    if user_was_muted:
        print(f"[Admin] Removido silêncio de {username}")
        target_socket, _ = find_user_by_name(username)
        if target_socket: send_system_message(target_socket, "Você não está mais silenciado.", CHAVE)
    else: print(f"[Admin] Usuário '{username}' não estava silenciado")

def warn_user(username, reason, CHAVE):
    target_socket, user_data = find_user_by_name(username)
    if target_socket:
        print(f"[Admin] Avisando {user_data['username']}")
        msg = f"Você recebeu um AVISO. Motivo: {reason}"
        send_system_message(target_socket, msg, CHAVE)
    else: print(f"[Admin] Usuário '{username}' não encontrado")

def broadcast_message(message_str, CHAVE, PORTA=-1, skip_client=None):
    encrypted_msg = encrypt_message(message_str, CHAVE)
    if not encrypted_msg:
        print("[Erro] Falha ao criptografar mensagem para broadcast.")
        return
    current_clients = {}
    with clients_lock: current_clients = clients.copy()
    for client_socket in current_clients.keys():
        if client_socket != skip_client:
            try: client_socket.send(encrypted_msg)
            except:
                threading.Thread(target=delete_client, args=[client_socket, CHAVE, PORTA]).start()

def delete_client(client_socket, CHAVE, PORTA, reason="saiu do chat"):
    username = "Alguém"
    with clients_lock:
        user_data = clients.pop(client_socket, None)
        if user_data: username = user_data["username"]
    with mute_lock:
        if username.lower() in mute_list: mute_list.pop(username.lower())
    try: client_socket.close()
    except: pass
    print(f"Conexão perdida com {username}")
    if PORTA != 0: update_lobby_count(PORTA, -1)
    if CHAVE: broadcast_message(f"<{username}> {reason}.", CHAVE, PORTA, None)

def reset_vote_state():
    global room_state
    with room_state_lock:
        room_state = {
            "vote_in_progress": False, "vote_type": None, "vote_target_user": None,
            "vote_target_socket": None, "votes_for": set(), "votes_against": set(),
            "voters": set()
        }

def check_vote_status(CHAVE, PORTA):
    action_to_take = None
    target_user = None
    vote_type = None
    result_message = ""
    with room_state_lock:
        if not room_state["vote_in_progress"]:
            return
        total_voters = len(room_state["voters"])
        if total_voters < 2:
            result_message = "\n[Votação] Votação cancelada: número insuficiente de eleitores\n"
            reset_vote_state()
        else:
            required_votes = (total_voters // 2) + 1
            votes_for_count = len(room_state["votes_for"])
            votes_against_count = len(room_state["votes_against"])
            total_votes_cast = votes_for_count + votes_against_count
            vote_passed = False
            vote_failed = False
            if votes_for_count >= required_votes:
                vote_passed = True
            elif votes_against_count >= required_votes or total_votes_cast == total_voters:
                vote_failed = True
            if vote_passed:
                target_user = room_state["vote_target_user"]
                vote_type = room_state["vote_type"]
                result_message = f"[Votação] A votação foi APROVADA ({votes_for_count} a favor). {target_user} será punido."
                action_to_take = vote_type
                reset_vote_state()
            elif vote_failed:
                result_message = f"[Votação] A votação FALHOU ({votes_for_count} a favor, {votes_against_count} contra). {room_state['vote_target_user']} não será punido."
                reset_vote_state()
    if result_message:
        broadcast_message(result_message, CHAVE, PORTA)
    if action_to_take == 'kick':
        kick_user(target_user, CHAVE, reason="foi expulso por votação")
    elif action_to_take == 'mute':
        mute_user(target_user, CHAVE, minutes=10)

def client_handler(client, CHAVE, PASSWORD, PORTA, is_public, CHAT_NAME, MAX_MEMBERS):
    username = ""
    username_lower = ""
    try:
        if PASSWORD is not None:
            password_attempt = client.recv(1024).decode('utf-8')
            if password_attempt != PASSWORD:
                print(f"Tentativa de conexão falhou: Senha errada")
                client.send(b"FAIL     ")
                client.close()
                return
        client.send(CHAVE)
        encrypted_username = client.recv(2048)
        username = decrypt_message(encrypted_username, CHAVE)
        if not username or not isinstance(username, str):
            print(f"[Erro] Nome de usuário inválido")
            client.send(b"FAIL_NAME")
            client.close()
            return
        username = username.strip()
        with clients_lock:
            for data in clients.values():
                if data["username"].lower() == username.lower():
                    print(f"Conexão recusada: Nome '{username}' já em uso")
                    client.send(b"FAIL_NAME")
                    client.close()
                    return
        client.send(b"OK_NAME  ")
        with clients_lock:
            clients[client] = {
                "username": username, "pm_blocked": False,
                "last_msg_time": time.time(), "msg_count": 0, "infractions": 0
            }
        print(f"'{username}' entrou no chat")
        if is_public: update_lobby_count(PORTA, +1)
        broadcast_message(f"<{username}> entrou no chat", CHAVE, PORTA, client)
        max_members_display = 'N/A' if MAX_MEMBERS == float('inf') else str(MAX_MEMBERS)
        welcome_msg = f"Você entrou no chat '{CHAT_NAME}'. {len(clients)}/{max_members_display} usuários online."
        send_system_message(client, welcome_msg, CHAVE)
        with mute_lock: mute_until = mute_list.get(username.lower())
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
                    mute_list.pop(username.lower())
    except Exception as e:
        print(f"Erro na autenticação: {e}")
        client.close()
        return

    while True:
        try:
            msg_criptografada = client.recv(2048)
            if not msg_criptografada: break
            msg = decrypt_message(msg_criptografada, CHAVE)
            if not msg or not isinstance(msg, str):
                continue
            msg = msg.strip()

            with mute_lock: mute_until = mute_list.get(username.lower())
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

            if not msg.startswith('/'):
                now = time.time()
                with clients_lock:
                    if client not in clients: break
                    user_data = clients[client]
                if now - user_data["last_msg_time"] < 5.0: user_data["msg_count"] += 1
                else: user_data["msg_count"] = 1
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
                        break

            if msg.lower() == '/help':
                help_text = "Comandos: /sair, /users, /info, /pm <user> <msg>, /togglepm, /votekick <user>, /votemute <user>, /vote <yes/no>"
                send_system_message(client, help_text, CHAVE)
            elif msg.lower() == '/togglepm':
                with clients_lock:
                    if client not in clients: break
                    clients[client]["pm_blocked"] = not clients[client]["pm_blocked"]
                    status = "BLOQUEADAS" if clients[client]["pm_blocked"] else "DESBLOQUEADAS"
                send_system_message(client, f"Mensagens privadas agora estão {status}.", CHAVE)
            elif msg.lower().startswith('/pm '):
                parts = msg.split(' ', 2)
                if len(parts) < 3: send_system_message(client, "Uso: /pm <username> <mensagem>", CHAVE)
                else:
                    target_username = parts[1]
                    pm_text = parts[2]
                    target_socket, target_data = find_user_by_name(target_username)
                    if target_socket:
                        if target_socket == client: send_system_message(client, "Não pode enviar PM para si mesmo", CHAVE)
                        elif target_data["pm_blocked"]: send_system_message(client, f"'{target_data['username']}' não aceita PMs", CHAVE)
                        else:
                            pm_to_target = f"[PM de {username}] {pm_text}"
                            encrypted_pm = encrypt_message(pm_to_target, CHAVE)
                            if encrypted_pm:
                                target_socket.send(encrypted_pm)
                            pm_confirm = f"[PM enviada para {target_data['username']}] {pm_text}"
                            encrypted_confirm = encrypt_message(pm_confirm, CHAVE)
                            if encrypted_confirm:
                                client.send(encrypted_confirm)
                    else: send_system_message(client, f"Usuário '{target_username}' não encontrado", CHAVE)
            elif msg.lower() == '/info':
                max_members_display = 'N/A' if MAX_MEMBERS == float('inf') else str(MAX_MEMBERS)
                with clients_lock: num_clients = len(clients)
                info = f"Sala: '{CHAT_NAME}', Membros: {num_clients}/{max_members_display}"
                send_system_message(client, info, CHAVE)
            elif msg.lower().startswith('/votekick ') or msg.lower().startswith('/votemute '):
                with room_state_lock:
                    if room_state["vote_in_progress"]: 
                        send_system_message(client, "Já existe uma votação em progresso", CHAVE)
                        continue
                    vote_type = 'kick' if 'votekick' in msg.lower() else 'mute'
                    target_username = msg.split(' ', 1)[1]
                    target_socket, target_data = find_user_by_name(target_username)
                    if not target_socket: 
                        send_system_message(client, f"Usuário '{target_username}' não encontrado", CHAVE)
                        continue
                    elif target_socket == client: 
                        send_system_message(client, "Não pode iniciar votação contra si mesmo", CHAVE)
                        continue
                    else:
                        with clients_lock: current_usernames = set(data["username"] for data in clients.values())
                        if len(current_usernames) < 2:
                            send_system_message(client, "São necessários pelo menos 2 usuários para votar", CHAVE)
                            continue
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
            elif msg.lower() == '/vote yes' or msg.lower() == '/vote no':
                with room_state_lock:
                    if not room_state["vote_in_progress"]: 
                        send_system_message(client, "Nenhuma votação em progresso", CHAVE)
                    elif username not in room_state["voters"]: 
                        send_system_message(client, "Não pode votar (não estava online no início)", CHAVE)
                    elif username in room_state["votes_for"] or username in room_state["votes_against"]: 
                        send_system_message(client, "Você já votou", CHAVE)
                    else:
                        vote = 'SIM'
                        if 'yes' in msg.lower(): 
                            room_state["votes_for"].add(username)
                        else: 
                            room_state["votes_against"].add(username)
                            vote = 'NÃO'
                        broadcast_message(f"[Votação] {username} votou {vote}.", CHAVE, PORTA)
                        check_vote_status(CHAVE, PORTA)
            elif msg.lower() == '/users':
                with clients_lock: user_list = ", ".join([data["username"] for data in clients.values()])
                response = f"[Sistema] Usuários online ({len(clients)}): {user_list}"
                encrypted_response = encrypt_message(response, CHAVE)
                if encrypted_response:
                    client.send(encrypted_response)
            elif msg:
                full_message = f"<{username}> {msg}"
                broadcast_message(full_message, CHAVE, PORTA, client)
        except ConnectionResetError:
            print(f"[Info] Conexão resetada por {username}")
            break
        except Exception as e:
            print(f"[Erro] Erro no cliente {username}: {e}")
            break
    delete_client(client, CHAVE, PORTA)

def main_render():
    """Versão automática para Render"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    CHAVE_SECRETA = generate_key()
    
    # Resetar estado global
    clients.clear()
    mute_list.clear()
    reset_vote_state()

    try:
        server.bind(('0.0.0.0', PORT))
        server.listen(5)
        print(Fore.GREEN + f"✅ Servidor ouvindo na porta {PORT}")
    except OSError as e:
        print(Fore.RED + f"❌ Erro ao iniciar servidor: {e}")
        return

    # Adicionar ao lobby (se público)
    add_server_to_lobby(CHAT_NAME, PORT, 'Ilimitado')

    # Iniciar thread de aceitação de conexões
    accept_thread = threading.Thread(
        target=accept_connections_loop,
        args=[server, CHAVE_SECRETA, PASSWORD, PORT, CHAT_NAME, float('inf')]
    )
    accept_thread.daemon = True
    accept_thread.start()

    print(Fore.GREEN + "\n✅ SERVIDOR ONLINE NO RENDER!")
    print(Fore.CYAN + f"🔗 URL: https://{HOSTNAME}")
    print(Fore.CYAN + f"🎯 Porta: {PORT}")
    print(Fore.YELLOW + "💡 Clientes podem conectar agora!")
    print(Fore.YELLOW + "📡 Aguardando conexões...")

    # Manter o servidor rodando indefinidamente
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n🛑 Servidor interrompido")
    finally:
        server.close()
        remove_server_from_lobby(PORT)

if __name__ == "__main__":
    main_render()