import os
import sys
import time
import threading
import subprocess
import pyautogui
import keyboard  # REQUISITO: pip install keyboard

# ==================================================
# ESCONDER O PROMPT ATUAL (SISTEMA OPERACIONAL)
# ==================================================
if sys.platform == "win32":
    import ctypes
    kernel32 = ctypes.WinDLL('kernel32')
    user32 = ctypes.WinDLL('user32')
    hWnd = kernel32.GetConsoleWindow()
    if hWnd:
        user32.ShowWindow(hWnd, 0)  # SW_HIDE = 0 (Esconde o prompt)

OOCULTAR_PROMPT = subprocess.STARTUPINFO()
OOCULTAR_PROMPT.dwFlags |= subprocess.STARTF_USESHOWWINDOW
OOCULTAR_PROMPT.wShowWindow = 0  # SW_HIDE

# ==================================================
# CONFIGURAÇÕES E MEMÓRIA GLOBAL (PERSISTENTE)
# ==================================================

IMG_DIR = "in_game"

RE_HOST_MAX = int(os.environ.get("RE_HOST_GLOBAL", "2"))
partidas_concluidas = int(os.environ.get("PARTIDAS_CONCLUIDAS_GLOBAL", "0"))

count_detectado = False

COORDS = {
    "DC_TOP_LEFT": (34, 28),     
    "DC2_PADRAO": (1615, 965),    
    "DC3_PADRAO": (1615, 965),    
    "FECHAR_PADRAO": (1883, 36),  
    "SIM_PADRAO": (846, 594),     
}

pyautogui.PAUSE = 0.1
pyautogui.FAILSAFE = True

# ==================================================
# ATUALIZAÇÃO DE STATUS
# ==================================================

def atualizar_painel_txt(partidas, max_rehost, ciclos):
    """Salva o status atual em um arquivo de texto para persistência."""
    try:
        with open("panel_status.txt", "w") as f:
            f.write(f"{partidas}\n{max_rehost}\n{ciclos}")
    except Exception:
        pass

# ==================================================
# FUNÇÃO DE PÂNICO (ESC)
# ==================================================

def verificar_esc():
    """Para o script imediatamente se o usuário apertar ESC."""
    keyboard.wait("esc")
    print("\a")
    os._exit(1)

# ==================================================
# HELPERS DE IMAGEM
# ==================================================

def img(nome):
    return os.path.join(IMG_DIR, nome)

def localizar(nome, confidence=0.85):
    try:
        return pyautogui.locateCenterOnScreen(img(nome), confidence=confidence)
    except Exception:
        return None

def clique_seguro(x, y, delay_depois=1.0):
    pyautogui.moveTo(x, y)
    time.sleep(0.2)
    pyautogui.click()
    time.sleep(delay_depois)

# ==================================================
# FLUXO DE SAÍDA E FECHAMENTO
# ==================================================

def fechar_e_desconectar_dota():
    """Desconecta da partida, fecha o Dota e chama o lobby.exe."""
    clique_seguro(*COORDS["DC_TOP_LEFT"], delay_depois=1.5)

    pos_dc2 = localizar("dc2.png")
    if pos_dc2:
        clique_seguro(*pos_dc2, delay_depois=0.5)
    else:
        clique_seguro(*COORDS["DC2_PADRAO"], delay_depois=0.5)

    pos_dc3 = None
    tempo_inicial = time.time()
    while (time.time() - tempo_inicial) < 15:
        pos_dc3 = localizar("dc3.png")
        if pos_dc3:
            break
        time.sleep(0.2)

    if pos_dc3:
        clique_seguro(*pos_dc3, delay_depois=2.5)  
    else:
        clique_seguro(*COORDS["DC3_PADRAO"], delay_depois=2.5)

    pos_fechar = localizar("fechar.png")
    if pos_fechar:
        clique_seguro(*pos_fechar, delay_depois=1.5)
    else:
        clique_seguro(*COORDS["FECHAR_PADRAO"], delay_depois=1.5)

    pos_sim = localizar("sim.png")
    if pos_sim:
        clique_seguro(*pos_sim, delay_depois=1.5)
    else:
        clique_seguro(*COORDS["SIM_PADRAO"], delay_depois=1.5)

    pw_atual = os.environ.get("PW_GLOBAL", "")
    
    caminho_lobby = "lobby.exe"
    if os.path.exists(caminho_lobby):
        subprocess.Popen([caminho_lobby, pw_atual], startupinfo=OOCULTAR_PROMPT)
    else:
        subprocess.Popen([sys.executable, "lobby.py", pw_atual], startupinfo=OOCULTAR_PROMPT)
    os._exit(0)

# ==================================================
# MONITORAMENTO DO COUNT E RE-HOST
# ==================================================

def monitorar_count_infinito():
    """Monitora o count.png de forma invisível."""
    global count_detectado, partidas_concluidas
    
    while True:
        pos_count = localizar("count.png")
        
        # 1. Identificou o Count na tela
        if pos_count and not count_detectado:
            print("\a")  # Beep sonoro
            count_detectado = True
            
        # 2. O Count sumiu da tela (Fim da partida)
        elif not pos_count and count_detectado:
            partidas_concluidas += 1
            count_detectado = False 
            
            # Atualiza o painel de texto com o progresso real
            atualizar_painel_txt(str(partidas_concluidas), str(RE_HOST_MAX), "0")
            
            if partidas_concluidas >= RE_HOST_MAX:
                os.environ["PARTIDAS_CONCLUIDAS_GLOBAL"] = "0"
                fechar_e_desconectar_dota()
            else:
                os.environ["PARTIDAS_CONCLUIDAS_GLOBAL"] = str(partidas_concluidas)
                time.sleep(2.0)
                
                caminho_in_game = "in_game.exe"
                if os.path.exists(caminho_in_game):
                    subprocess.Popen([caminho_in_game], startupinfo=OOCULTAR_PROMPT)
                else:
                    subprocess.Popen([sys.executable, "in_game.py"], startupinfo=OOCULTAR_PROMPT)
                os._exit(0)
            break
            
        time.sleep(2.0)

# ==================================================
# EXECUÇÃO PRINCIPAL
# ==================================================

if __name__ == "__main__":
    # Inicia a thread de pânico
    thread_panic = threading.Thread(target=verificar_esc, daemon=True)
    thread_panic.start()

    # Inicializa o painel com os dados iniciais corretos antes do loop
    atualizar_painel_txt(str(partidas_concluidas), str(RE_HOST_MAX), "0")

    # Inicia o monitoramento principal
    monitorar_count_infinito()