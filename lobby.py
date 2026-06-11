import os
import sys
import time
import subprocess
import threading
import pyautogui
import keyboard  # REQUISITO: pip install keyboard

# ==================================================
# CONFIG
# ==================================================

STEAM_EXE = r"C:\Program Files (x86)\Steam\steam.exe"
IMG_DIR = "img"

# Resgata a senha global enviada pelo start.py
PW = os.environ.get("PW_GLOBAL", sys.argv[1] if len(sys.argv) > 1 else "")

# Coordenadas fixas de Backup (Apenas se a imagem falhar completamente)
COORDS_BACKUP = {
    "LISTA": (902, 86),
    "LOBBY": (916, 835),
    "OK": (1018, 608),
    "ATT": (1554, 174),
    "GAME": (447, 239),
    "ERRO": (965, 612)
}

# ==================================================
# PYAUTOGUI
# ==================================================

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True  # Pânico: Arrastar o mouse pro canto da tela para o bot

# ==================================================
# FUNÇÃO DE PARADA DE EMERGÊNCIA (ESC)
# ==================================================

def verificar_esc():
    """Fica rodando em segundo plano. Se apertar ESC, fecha o script imediatamente."""
    keyboard.wait("esc")
    print("\n[AVISO] Execução interrompida pelo usuário via tecla ESC!")
    os._exit(1)

# ==================================================
# HELPERS DE IMAGEM (TELA CHEIA)
# ==================================================

def img(nome):
    return os.path.join(IMG_DIR, nome)

def localizar(nome, confidence=0.80):
    """Procura a imagem na tela inteira com tolerância para variações gráficas."""
    try:
        return pyautogui.locateCenterOnScreen(img(nome), confidence=confidence)
    except Exception:
        return None

def esperar(nome, confidence=0.80):
    """Aguarda pacientemente a imagem aparecer na tela cheia."""
    print(f"[AGUARDANDO] {nome} na tela cheia...")
    while True:
        pos = localizar(nome, confidence)
        if pos:
            print(f"[OK] {nome} encontrado!")
            return pos
        time.sleep(0.2)

def clique_seguro(pos_imagem, coordenada_backup, pausa_antes=0.3):
    """Clica no centro da imagem encontrada. Se não achar, usa o backup."""
    if pos_imagem:
        pyautogui.moveTo(pos_imagem[0], pos_imagem[1])
        time.sleep(pausa_antes)
        pyautogui.click()
    else:
        # Se a imagem falhar por milissegundos, usa a coordenada padrão para não travar
        pyautogui.moveTo(*coordenada_backup)
        time.sleep(pausa_antes)
        pyautogui.click()

# ==================================================
# DOTA
# ==================================================

def abrir_dota():
    print("[INFO] Abrindo Dota 2")
    if not os.path.isfile(STEAM_EXE):
        raise FileNotFoundError(f"Steam não encontrada: {STEAM_EXE}")

    subprocess.Popen(
        [STEAM_EXE, "-applaunch", "570"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

# ==================================================
# MENU PRINCIPAL
# ==================================================

def etapa_menu():
    print("[INFO] Aguardando o menu principal do Dota carregar...")
    while True:
        # Se achar o botão LISTA, o menu estabilizou
        lista = localizar("lista.png")
        if lista:
            print("[OK] Botão LISTA visível.")
            break

        # Se o Dota abrir em uma aba errada, clica em image.png para resetar a tela
        image = localizar("image.png")
        if image:
            clique_seguro(image, coordenada_backup=COORDS_BACKUP["LISTA"])

        time.sleep(0.2)

    # Clica no botão LISTA
    print("[INFO] Clicando no botão LISTA...")
    lista_pos = localizar("lista.png")
    clique_seguro(lista_pos, coordenada_backup=COORDS_BACKUP["LISTA"])
    time.sleep(0.8)

    # Clica no botão LOBBY
    print("[INFO] Clicando no botão LOBBY...")
    lobby_pos = localizar("lobby.png")
    clique_seguro(lobby_pos, coordenada_backup=COORDS_BACKUP["LOBBY"], pausa_antes=0.4)

# ==================================================
# SENHA
# ==================================================

def etapa_senha():
    # Espera o botão OK do painel de senha surgir na tela
    ok_pos = esperar("ok.png")
    time.sleep(0.4)

    print("[INFO] Limpando o campo de texto por segurança...")
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("backspace")
    time.sleep(0.1)

    print(f"[INFO] Digitando a senha: {PW}")
    pyautogui.write(PW, interval=0.05)
    time.sleep(0.2)

    print("[INFO] Confirmando senha...")
    clique_seguro(ok_pos, coordenada_backup=COORDS_BACKUP["OK"])
    print("[OK] Senha enviada com sucesso.")

# ==================================================
# FLUXO ACEITAR
# ==================================================

def flujo_aceitar():
    print("[INFO] Entrando no fluxo aceitar")
    while True:
        erro = localizar("erro.png")
        if erro:
            print("[ERRO] Popup detectado! Clicando na imagem do erro...")
            clique_seguro(erro, coordenada_backup=COORDS_BACKUP["ERRO"])
            time.sleep(0.05)

        fim = localizar("fim.png")
        if fim:
            print("[OK] fim.png encontrado! Iniciando partida...")
            subprocess.Popen([sys.executable, "in_game.py"])
            return

        time.sleep(0.05)

# ==================================================
# BUSCA DE LOBBY
# ==================================================

def etapa_lobby():
    esperar("200.png")
    print("[INFO] Iniciando busca automatizada por lobby...")

    dentro_da_sala = False

    while True:
        # 1. TRATAMENTO DE ERRO (Prioridade Máxima)
        erro = localizar("erro.png")
        if erro:
            print("[ERRO] Popup detectado! Fechando...")
            clique_seguro(erro, coordenada_backup=COORDS_BACKUP["ERRO"], pausa_antes=0.1)
            time.sleep(0.3)
            dentro_da_sala = False
            
            # Força o clique no atualizar para limpar o estado visual
            att_pos = localizar("att.png")
            clique_seguro(att_pos, coordenada_backup=COORDS_BACKUP["ATT"], pausa_antes=0.1)
            time.sleep(0.6)
            continue

        # 2. ACEITAR
        aceitar = localizar("aceitar.png")
        if aceitar:
            print("[OK] ACEITAR encontrado! Entrando no fluxo de confirmação...")
            clique_seguro(aceitar, coordenada_backup=COORDS_BACKUP["OK"])
            flujo_aceitar()
            return

        if dentro_da_sala:
            print("[INFO] Já estamos dentro da sala. Aguardando o host iniciar...")
            time.sleep(0.2)
            if not localizar("sala.png"):
                print("[AVISO] Sala sumiu ou fomos kickados. Resetando busca...")
                dentro_da_sala = False
            continue

        # 3. VERIFICAÇÃO SE ENTROU NA SALA
        if localizar("sala.png"):
            print("[OK] Imagem SALA detectada! Congelando cliques de busca.")
            dentro_da_sala = True
            continue

        # 4. ENTRAR NO JOGO (GAME)
        game = localizar("game.png", confidence=0.90)
        if game:
            print("[OK] GAME encontrado! Executando clique...")
            clique_seguro(game, coordenada_backup=COORDS_BACKUP["GAME"])
            
            print("[INFO] Executando segundo clique de garantia...")
            pyautogui.click()
            time.sleep(0.5)
            continue

        # 5. ATUALIZAR (ATT)
        print("[INFO] Atualizando lista de salas (ATT)...")
        att_pos = localizar("att.png")
        clique_seguro(att_pos, coordenada_backup=COORDS_BACKUP["ATT"], pausa_antes=0.1)
        time.sleep(0.6)

# ==================================================
# MAIN
# ==================================================

def executar():
    thread_panic = threading.Thread(target=verificar_esc, daemon=True)
    thread_panic.start()

    abrir_dota()
    etapa_menu()
    etapa_senha()
    etapa_lobby()

if __name__ == "__main__":
    executar()