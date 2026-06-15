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
def save_status(partidas: int, rehost_max: int, ciclos: int):
    try:
        with open(STATUS_FILE, "w") as f:
            f.write(f"{partidas}\n{rehost_max}\n{ciclos}")
    except Exception:
        pass

def kill_all_children():
    global processo_lobby, processo_painel
    for proc in (processo_lobby, processo_painel):
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    if sys.platform == "win32":
        for target in ["lobby.exe", "in_game.exe", "painel.exe"]:
            os.system(f'taskkill /f /im {target} >nul 2>&1')
        for script in ["lobby.py", "in_game.py", "painel.py"]:
            os.system(f'wmic process where "commandline like \'%{script}%\'" delete >nul 2>&1')

def on_close():
    kill_all_children()
    root.destroy()
    os._exit(0)

# ==================================================
# MONITOR DE PROCESSOS  ← novo
# ==================================================
def watch_processes():
    """
    Roda a cada 1s via root.after.
    Se o processo lobby morreu (por ESC, crash ou fim normal),
    reabilita o botão Start e reseta o label de status.
    """
    global processo_lobby

    if processo_lobby is not None:
        exit_code = processo_lobby.poll()   # None = ainda vivo
        if exit_code is not None:
            # Processo morreu — independente do motivo
            processo_lobby = None
            btn_start.config(state="normal")
            label_status.config(
                text=f"Encerrado (código {exit_code}). Pronto para reiniciar.",
                foreground="gray"
            )

    root.after(1000, watch_processes)   # agenda próxima verificação

# ==================================================
# ACTIONS
# ==================================================
def start():
    global processo_lobby, processo_painel

    pw     = entry_pw.get().strip()
    rehost = entry_rehost.get().strip() or "1"

    if not rehost.isdigit() or int(rehost) < 1:
        label_status.config(text="Re-Host deve ser um número ≥ 1", foreground="red")
        return

    os.environ["PW_GLOBAL"]                  = pw
    os.environ["RE_HOST_GLOBAL"]             = rehost
    os.environ["PARTIDAS_CONCLUIDAS_GLOBAL"] = "0"
    os.environ["CICLOS_GLOBAL"]              = "0"

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
    root.geometry("300x240")
    root.resizable(False, False)
    root.protocol("WM_DELETE_WINDOW", on_close)

    frame = ttk.Frame(root, padding=15)
    frame.pack(fill="both", expand=True)

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

    # Inicia o monitor de processos imediatamente
    watch_processes()

    root.mainloop()