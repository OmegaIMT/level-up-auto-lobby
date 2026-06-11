import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk

def iniciar_lobby():
    pw = entry_pw.get().strip()
    re_host = entry_rehost.get().strip()

    if not re_host:
        re_host = "1"

    # Salva na memória do sistema para o lobby e in_game usarem
    os.environ["RE_HOST_GLOBAL"] = re_host
    os.environ["PW_GLOBAL"] = pw

    print(f"[INFO] Iniciando ciclo com PW: {pw} e Re-Host: {re_host}")

    # Abre o lobby.py de forma totalmente independente
    subprocess.Popen([
        sys.executable, 
        "lobby.py", 
        pw
    ])
    
    # Opcional: Se você quiser que o painel feche sozinho após dar Start, 
    # descomente a linha abaixo tirando o '#'
    # root.destroy()

# A proteção abaixo garante que a interface SÓ vai abrir se você clicar direto no start.py
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Configuração")
    root.geometry("300x220")
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=15)
    frame.pack(fill="both", expand=True)

    # Campo PW
    ttk.Label(frame, text="PW").pack(anchor="w")
    entry_pw = ttk.Entry(frame, width=30)
    entry_pw.pack(fill="x", pady=(0, 10))

    # Campo RE-HOST
    ttk.Label(frame, text="Re-Host (Número)").pack(anchor="w")
    entry_rehost = ttk.Entry(frame, width=30)
    entry_rehost.pack(fill="x", pady=(0, 15))

    # Botão Start
    ttk.Button(frame, text="Start", command=iniciar_lobby).pack(fill="x")

    root.mainloop()