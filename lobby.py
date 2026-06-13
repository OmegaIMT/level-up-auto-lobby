import os
import sys
import time
import threading
import subprocess  # Alterado para suportar execução oculta
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

# Configuração para que os processos filhos também nasçam sem janela preta
OOCULTAR_PROMPT = subprocess.STARTUPINFO()
OOCULTAR_PROMPT.dwFlags |= subprocess.STARTF_USESHOWWINDOW
OOCULTAR_PROMPT.wShowWindow = 0  # SW_HIDE

# ==================================================
# CONFIGURAÇÃO INTERNACIONAIS E DIRETÓRIOS
# ==================================================

IMG_DIR = "img"

PW = os.environ.get("PW_GLOBAL", sys.argv[1] if len(sys.argv) > 1 else "4433")

# ==================================================
# CONFIGURAÇÕES DO PYAUTOGUI
# ==================================================

pyautogui.PAUSE = 0.03
pyautogui.FAILSAFE = True  

# ==================================================
# FUNÇÃO DE PARADA DE EMERGÊNCIA (ESC)
# ==================================================

def verificar_esc():
    """Fica rodando em segundo plano. Se apertar ESC, fecha o script imediatamente."""
    keyboard.wait("esc")
    print("\a")  # Beep de aviso antes de fechar
    os._exit(1)

# ==================================================
# HELPERS DE JANELA (WINDOWS)
# ==================================================

def focar_dota():
    """Procura a janela do Dota 2 pelo título e a traz para o primeiro plano."""
    if sys.platform == "win32":
        try:
            # O título padrão da janela do jogo é "Dota 2"
            hwnd_dota = user32.FindWindowW(None, "Dota 2")
            if hwnd_dota:
                # Se a janela estiver minimizada, restaura
                user32.ShowWindow(hwnd_dota, 9)  # SW_RESTORE = 9
                # Traz para frente e foca
                user32.SetForegroundWindow(hwnd_dota)
                time.sleep(1.0)  # Tempo para o Windows processar a transição
                return True
        except Exception:
            pass
    return False

# ==================================================
# HELPERS DE IMAGEM (TELA CHEIA)
# ==================================================

def img(nome):
    return os.path.join(IMG_DIR, nome)

def localizar(nome, confidence=0.80):
    try:
        return pyautogui.locateCenterOnScreen(img(nome), confidence=confidence)
    except Exception:
        return None

def esperar(nome, confidence=0.80, timeout=60):
    inicio = time.time()
    while True:
        pos = localizar(nome, confidence)
        if pos:
            return pos
        if (time.time() - inicio) > timeout:
            return None
        time.sleep(0.3)

def clique_seguro(pos_imagem, pausa_antes=0.3):
    if pos_imagem:
        pyautogui.moveTo(pos_imagem[0], pos_imagem[1])
        time.sleep(pausa_antes)
        pyautogui.click()
        return True
    return False

# ==================================================
# FLUXO DE EXECUÇÃO DO JOGO
# ==================================================

def abrir_dota():
    """Foca o Dota 2 se já estiver aberto, ou inicia via Steam caso não esteja."""
    # Tenta focar a janela primeiro
    if focar_dota():
        return  # Se achou e focou, não precisa abrir de novo

    # Caso não encontre a janela aberta, inicia o processo
    try:
        subprocess.Popen(["cmd", "/c", "start", "steam://run/570"], startupinfo=OOCULTAR_PROMPT)
        # Espera um tempo inicial para o processo começar a carregar a janela
        time.sleep(5.0)
    except Exception:
        os._exit(1)

def etapa_menu():
    if not os.path.exists(IMG_DIR):
        os._exit(1)

    while True:
        # Garante foco contínuo no início da detecção caso o jogo mude de estado
        focar_dota()
        
        lista = localizar("lista.png")
        if lista:
            break

        image = localizar("image.png")
        if image:
            clique_seguro(image)

        time.sleep(0.5)

    clique_seguro(localizar("lista.png"))
    time.sleep(0.8)

    clique_seguro(esperar("lobby.png"), pausa_antes=0.4)

def etapa_senha():
    ok_pos = esperar("ok.png")
    if not ok_pos:
        return
    
    time.sleep(0.3)
    focar_dota()  # Garante foco antes de enviar comandos de teclado genéricos

    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("backspace")
    time.sleep(0.1)

    pyautogui.write(PW, interval=0.05)
    time.sleep(0.2)

    clique_seguro(ok_pos)

def fluxo_aceitar():
    while True:
        erro = localizar("erro.png")
        if erro:
            clique_seguro(erro)
            time.sleep(0.1)

        fim = localizar("fim.png")
        if fim:
            caminho_game = "in_game.exe"
            if os.path.exists(caminho_game):
                subprocess.Popen([caminho_game], startupinfo=OOCULTAR_PROMPT)
            else:
                subprocess.Popen([sys.executable, "in_game.py"], startupinfo=OOCULTAR_PROMPT)
            return

        time.sleep(0.1)

def etapa_lobby():
    if not esperar("200.png", timeout=30):
        pass
        
    dentro_da_sala = False

    while True:
        erro = localizar("erro.png")
        if erro:
            clique_seguro(erro, pausa_antes=0.1)
            time.sleep(0.3)
            dentro_da_sala = False
            
            clique_seguro(localizar("att.png"), pausa_antes=0.1)
            continue

        aceitar = localizar("aceitar.png")
        if aceitar:
            clique_seguro(aceitar)
            fluxo_aceitar()
            return

        if dentro_da_sala:
            time.sleep(0.3)
            if not localizar("sala.png"):
                dentro_da_sala = False
            continue

        if localizar("sala.png"):
            dentro_da_sala = True
            continue

        game = localizar("game.png", confidence=0.90)
        if game:
            clique_seguro(game)
            time.sleep(0.2)
            pyautogui.click()  
            time.sleep(0.5)
            continue

        att_pos = localizar("att.png")
        if att_pos:
            clique_seguro(att_pos, pausa_antes=0.1)
        time.sleep(0.3)

# ==================================================
# EXECUÇÃO PRINCIPAL
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