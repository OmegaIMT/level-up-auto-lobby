import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk

# Ocultação do prompt atual
if sys.platform == "win32":
    import ctypes
    hWnd = ctypes.WinDLL('kernel32').GetConsoleWindow()
    if hWnd:
        ctypes.WinDLL('user32').ShowWindow(hWnd, 0) # SW_HIDE

OOCULTAR_PROMPT = subprocess.STARTUPINFO()
OOCULTAR_PROMPT.dwFlags |= subprocess.STARTF_USESHOWWINDOW
OOCULTAR_PROMPT.wShowWindow = 0

processo_lobby = None
processo_painel = None # Nova referência para o painel

def atualizar_painel_txt(partidas, max_rehost, ciclos):
    """Escreve os dados de forma ultra leve no arquivo para o painel ler."""
    try:
        with open("panel_status.txt", "w") as f:
            f.write(f"{partidas}\n{max_rehost}\n{ciclos}")
    except Exception:
        pass

def encerrar_tudo():
    global processo_lobby, processo_painel
    print("[INFO] Fechando interface principal. Limpando processos...")
    
    # Fecha o Lobby
    if processo_lobby and processo_lobby.poll() is None:
        try:
            processo_lobby.terminate()
        except Exception:
            pass

    # Fecha o Painel
    if processo_painel and processo_painel.poll() is None:
        try:
            processo_painel.terminate()
        except Exception:
            pass

    # Força a limpeza geral no Windows por garantia
    try:
        if sys.platform == "win32":
            os.system("taskkill /f /im lobby.exe >nul 2>&1")
            os.system("taskkill /f /im in_game.exe >nul 2>&1")
            os.system("taskkill /f /im painel.exe >nul 2>&1")
    except Exception:
        pass

    root.destroy()
    os._exit(0)

def iniciar_lobby():
    global processo_lobby, processo_painel
    
    pw = entry_pw.get().strip()
    re_host = entry_rehost.get().strip()

    if not re_host:
        re_host = "1"

    # Define os estados iniciais no ambiente do Windows
    os.environ["RE_HOST_GLOBAL"] = re_host
    os.environ["PW_GLOBAL"] = pw
    os.environ["PARTIDAS_CONCLUIDAS_GLOBAL"] = "0"
    if "CICLOS_GLOBAL" not in os.environ:
        os.environ["CICLOS_GLOBAL"] = "0"

    # AJUSTE AQUI: Cria/limpa o arquivo txt com os dados iniciais corretos assim que clica em Start
    atualizar_painel_txt("0", re_host, "0")

    # 1. INICIA O LOBBY (Com prompt ocultado)
    caminho_lobby = "lobby.exe"
    if os.path.exists(caminho_lobby):
        processo_lobby = subprocess.Popen([caminho_lobby, pw], startupinfo=OOCULTAR_PROMPT)
    else:
        processo_lobby = subprocess.Popen([sys.executable, "lobby.py", pw], startupinfo=OOCULTAR_PROMPT)
    
    # 2. INICIA O PAINEL OVERLAY (Com prompt ocultado)
    caminho_painel = "painel.exe"
    if os.path.exists(caminho_painel):
        processo_painel = subprocess.Popen([caminho_painel], startupinfo=OOCULTAR_PROMPT)
    else:
        processo_painel = subprocess.Popen([sys.executable, "painel.py"], startupinfo=OOCULTAR_PROMPT)

    print("[INFO] Processos Iniciados. Minimizando a janela start...")
    root.iconify()

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Configuração")
    root.geometry("300x220")
    root.resizable(False, False)

    root.protocol("WM_DELETE_WINDOW", encerrar_tudo)

    frame = ttk.Frame(root, padding=15)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="PW").pack(anchor="w")
    entry_pw = ttk.Entry(frame, width=30)
    entry_pw.pack(fill="x", pady=(0, 10))

    ttk.Label(frame, text="Re-Host (Número)").pack(anchor="w")
    entry_rehost = ttk.Entry(frame, width=30)
    entry_rehost.pack(fill="x", pady=(0, 15))

    ttk.Button(frame, text="Start", command=iniciar_lobby).pack(fill="x")

    root.mainloop()