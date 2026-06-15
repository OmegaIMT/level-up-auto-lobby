import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk

# ==================================================
# HIDE CONSOLE
# ==================================================
if sys.platform == "win32":
    import ctypes
    hWnd = ctypes.WinDLL('kernel32').GetConsoleWindow()
    if hWnd:
        ctypes.WinDLL('user32').ShowWindow(hWnd, 0)

HIDDEN_WINDOW = subprocess.STARTUPINFO()
HIDDEN_WINDOW.dwFlags     |= subprocess.STARTF_USESHOWWINDOW
HIDDEN_WINDOW.wShowWindow  = 0

STATUS_FILE = "panel_status.txt"

processo_lobby  = None
processo_painel = None

# ==================================================
# HELPERS
# ==================================================
def save_status(partidas: int, rehost_max: int, ciclos: int) -> None:
    try:
        with open(STATUS_FILE, "w") as f:
            f.write(f"{partidas}\n{rehost_max}\n{ciclos}")
    except Exception:
        pass

def kill_all_children() -> None:
    """Encerra lobby, painel e quaisquer processos filhos pelo nome."""
    global processo_lobby, processo_painel

    # Termina handles conhecidos primeiro
    for proc in (processo_lobby, processo_painel):
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    if sys.platform == "win32":
        # Mata executáveis compilados
        for target in ["lobby.exe", "in_game.exe", "painel.exe"]:
            os.system(f'taskkill /f /im {target} >nul 2>&1')
        # Mata scripts Python rodando via interpretador
        for script in ["lobby.py", "in_game.py", "painel.py"]:
            os.system(
                f'wmic process where "commandline like \'%{script}%\'" delete >nul 2>&1'
            )

    processo_lobby  = None
    processo_painel = None

def on_close() -> None:
    kill_all_children()
    root.destroy()
    os._exit(0)

# ==================================================
# MONITOR DE PROCESSOS
# ==================================================
def watch_processes() -> None:
    """
    Roda a cada 1s via root.after.
    Se o lobby morreu (ESC, crash ou fim normal), reabilita o botão
    Start e encerra o painel junto — os dois sobem e descem juntos.
    """
    global processo_lobby, processo_painel

    if processo_lobby is not None:
        exit_code = processo_lobby.poll()   # None = ainda vivo
        if exit_code is not None:
            # Lobby encerrou → garante que o painel também some
            processo_lobby = None
            kill_all_children()             # mata painel e qualquer sobrevivente
            btn_start.config(state="normal")
            label_status.config(
                text=f"Encerrado (código {exit_code}). Pronto para reiniciar.",
                foreground="gray"
            )

    root.after(1000, watch_processes)

# ==================================================
# ACTIONS
# ==================================================
def start() -> None:
    global processo_lobby, processo_painel

    pw         = entry_pw.get().strip()
    rehost     = entry_rehost.get().strip() or "1"
    lobby_name = entry_lobby_name.get().strip()

    if not rehost.isdigit() or int(rehost) < 1:
        label_status.config(text="Re-Host deve ser um número ≥ 1", foreground="red")
        return

    if not lobby_name:
        label_status.config(text="Informe o Nome do Lobby", foreground="red")
        return

    os.environ["PW_GLOBAL"]                  = pw
    os.environ["RE_HOST_GLOBAL"]             = rehost
    os.environ["PARTIDAS_CONCLUIDAS_GLOBAL"] = "0"
    os.environ["CICLOS_GLOBAL"]              = "0"
    os.environ["LOBBY_NAME_GLOBAL"]          = lobby_name   # ← novo

    save_status(0, int(rehost), 0)

    if os.path.exists("lobby.exe"):
        processo_lobby = subprocess.Popen(["lobby.exe", pw], startupinfo=HIDDEN_WINDOW)
    else:
        processo_lobby = subprocess.Popen(
            [sys.executable, "lobby.py", pw], startupinfo=HIDDEN_WINDOW
        )

    if os.path.exists("painel.exe"):
        processo_painel = subprocess.Popen(["painel.exe"], startupinfo=HIDDEN_WINDOW)
    else:
        processo_painel = subprocess.Popen(
            [sys.executable, "painel.py"], startupinfo=HIDDEN_WINDOW
        )

    btn_start.config(state="disabled")
    label_status.config(text="Iniciado! Minimizando...", foreground="green")
    root.after(1200, root.iconify)

# ==================================================
# UI
# ==================================================
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Bot Config")
    root.geometry("300x290")
    root.resizable(False, False)
    root.protocol("WM_DELETE_WINDOW", on_close)

    frame = ttk.Frame(root, padding=15)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="Nome do Lobby").pack(anchor="w")
    entry_lobby_name = ttk.Entry(frame, width=30)
    entry_lobby_name.pack(fill="x", pady=(0, 10))

    ttk.Label(frame, text="Senha (PW)").pack(anchor="w")
    entry_pw = ttk.Entry(frame, width=30, show="")
    entry_pw.pack(fill="x", pady=(0, 10))

    ttk.Label(frame, text="Re-Host (partidas por ciclo)").pack(anchor="w")
    entry_rehost = ttk.Entry(frame, width=30)
    entry_rehost.pack(fill="x", pady=(0, 10))

    btn_start = ttk.Button(frame, text="Start", command=start)
    btn_start.pack(fill="x", pady=(5, 0))

    label_status = ttk.Label(frame, text="", foreground="gray")
    label_status.pack(pady=(8, 0))

    watch_processes()
    root.mainloop()