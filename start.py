import os
import sys
import subprocess
import json
import tkinter as tk
from tkinter import ttk

# ==================================================
# HIDE CONSOLE
# ==================================================
if sys.platform == "win32":
    import ctypes

    hWnd = ctypes.WinDLL("kernel32").GetConsoleWindow()  # cspell:disable-line
    if hWnd:
        ctypes.WinDLL("user32").ShowWindow(hWnd, 0)  # cspell:disable-line

# cspell:disable-next-line
HIDDEN_WINDOW = subprocess.STARTUPINFO()
HIDDEN_WINDOW.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # cspell:disable-line
HIDDEN_WINDOW.wShowWindow = 0  # cspell:disable-line

STATUS_FILE = "status.json"
CONFIG_FILE = "config.json"

processo_lobby = None
processo_painel = None

# ==================================================
# CONFIGURATIONS & LANGUAGES
# ==================================================
# Aqui é onde as pastas são mapeadas. O app vai procurar em: language/<valor>/start.json
LANGUAGES = {
    "Português (Brasil)": "pt-br",
    "English": "en-us",
    "Русский": "ru",
    "中文": "zh-cn",
}

RESOLUTIONS = {
    "1920x1080": "1920x1080",
    "1600x900": "1600x900",
    "1366x768": "1366x768",
}

# Iniciado vazio para forçar o carregamento do JSON
TEXT = {}


def load_language(language_folder: str) -> None:
    """
    Carrega o arquivo de idioma do start.json correspondente baseado na pasta externa
    """
    global TEXT
    path = os.path.join("language", language_folder, "start.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            dados = json.load(f)
            if isinstance(dados, dict):
                TEXT.update(dados)
    except Exception as e:
        print(f"Erro ao carregar idioma {language_folder}: {e}")


def atualizar_interface_idioma(event=None) -> None:
    """
    Detecta a mudança no Combobox, recarrega o JSON correspondente e atualiza os elementos visuais
    """
    language_display = language_var.get()
    language_folder = LANGUAGES.get(language_display, "pt-br")

    # Recarrega o dicionário TEXT com o arquivo da pasta selecionada
    load_language(language_folder)

    # Atualiza os componentes da janela em tempo real
    root.title(TEXT.get("title", "Auto Lobby Level Up"))
    lbl_pw1.config(text=TEXT.get("password_1", ""))
    lbl_pw2.config(text=TEXT.get("password_2", ""))
    lbl_pw3.config(text=TEXT.get("password_3", ""))
    lbl_interval.config(text=TEXT.get("password_interval", ""))
    lbl_rehost.config(text=TEXT.get("rehost", ""))
    lbl_language.config(text=TEXT.get("language", ""))
    lbl_resolution.config(text=TEXT.get("resolution", ""))
    chk_crystal.config(text=TEXT.get("crystal", ""))
    chk_equipment.config(text=TEXT.get("equipment", ""))
    chk_support.config(text=TEXT.get("support", ""))
    btn_start.config(text=TEXT.get("start", ""))
    label_footer.config(text=TEXT.get("footer", ""))

    # Limpa mensagens de erro antigas ao trocar de idioma
    label_status.config(text="")


# ==================================================
# HELPERS
# ==================================================
def save_status(partidas: int, rehost_max: int, ciclos: int, current_pw: str = "") -> None:
    """
    Grava o status inicial em status.json (mesmo formato que o lobby.py usa
    para atualizações ao vivo: partidas, rehost_max, ciclos, current_password,
    password_deadline). O lobby.py é quem mantém esse arquivo atualizado
    depois que a sessão começa; aqui só inicializamos com os valores de start.
    """
    payload = {
        "partidas": partidas,
        "rehost_max": rehost_max,
        "ciclos": ciclos,
        "current_password": current_pw,
        "password_deadline": 0.0,
    }
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def save_config(config: dict) -> None:
    """
    Grava a configuração da sessão em config.json.
    O lobby.py passa a ler esse arquivo em vez de variáveis de ambiente,
    evitando recriar/reprocessar argumentos e permitindo reler o intervalo
    de troca de senha sob demanda (sem polling constante via env).
    """
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar config: {e}")


def kill_all_children() -> None:
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
            # cspell:disable-next-line
            os.system(f'wmic process where "commandline like \'%{script}%\'" delete >nul 2>&1')

    processo_lobby = None
    processo_painel = None


def on_close() -> None:
    kill_all_children()
    root.destroy()
    os._exit(0)


def watch_processes() -> None:
    root.after(1000, watch_processes)


# ==================================================
# ACTIONS
# ==================================================
def start() -> None:
    global processo_lobby, processo_painel

    if processo_lobby and processo_lobby.poll() is None:
        return

    pw1 = entry_pw1.get().strip()
    pw2 = entry_pw2.get().strip()
    pw3 = entry_pw3.get().strip()
    interval = entry_interval.get().strip() or "1"
    rehost = entry_rehost.get().strip() or "1"

    language_display = language_var.get()
    language_folder = LANGUAGES.get(language_display, "pt-br")
    resolution = resolution_var.get()

    if not interval.isdigit() or int(interval) < 1:
        label_status.config(text=TEXT.get("error_interval", "Error"), foreground="red")
        return

    if not rehost.isdigit() or int(rehost) < 1:
        label_status.config(text=TEXT.get("error_rehost", "Error"), foreground="red")
        return

    config = {
        "passwords": [pw1, pw2, pw3],
        "password_interval_minutes": int(interval),
        "rehost_max": int(rehost),
        "partidas_concluidas": 0,
        "ciclos": 0,
        "language": language_folder,
        "resolution": resolution,
        "crystal": crystal_var.get(),
        "equipment": equipment_var.get(),
        "support": support_var.get(),
    }
    save_config(config)
    save_status(0, int(rehost), 0, current_pw=pw1)

    if os.path.exists("lobby.exe"):
        processo_lobby = subprocess.Popen(["lobby.exe", CONFIG_FILE], startupinfo=HIDDEN_WINDOW)
    else:
        processo_lobby = subprocess.Popen(
            [sys.executable, "lobby.py", CONFIG_FILE], startupinfo=HIDDEN_WINDOW
        )

    if os.path.exists("painel.exe"):
        processo_painel = subprocess.Popen(["painel.exe"], startupinfo=HIDDEN_WINDOW)
    else:
        processo_painel = subprocess.Popen([sys.executable, "painel.py"], startupinfo=HIDDEN_WINDOW)

    status_msg = TEXT.get("status_started", "Iniciado")
    label_status.config(text=f"{status_msg} ({language_folder})", foreground="green")
    root.after(1200, root.iconify)


# ==================================================
# UI INITIALIZATION
# ==================================================
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("420x420")
    root.resizable(False, False)

    if os.path.exists("level-up.ico"):
        try:
            root.iconbitmap("level-up.ico")  # cspell:disable-line
        except Exception:
            pass

    root.protocol("WM_DELETE_WINDOW", on_close)

    # Frame Principal Único
    frame = ttk.Frame(root, padding=15)
    frame.pack(fill="both", expand=True)

    # Senhas (3 colunas lado a lado)
    row_passwords = ttk.Frame(frame)
    row_passwords.pack(fill="x", pady=(0, 12))
    row_passwords.columnconfigure(0, weight=1)
    row_passwords.columnconfigure(1, weight=1)
    row_passwords.columnconfigure(2, weight=1)

    col_pw1 = ttk.Frame(row_passwords)
    col_pw1.grid(row=0, column=0, sticky="ew", padx=(0, 6))

    col_pw2 = ttk.Frame(row_passwords)
    col_pw2.grid(row=0, column=1, sticky="ew", padx=6)

    col_pw3 = ttk.Frame(row_passwords)
    col_pw3.grid(row=0, column=2, sticky="ew", padx=(6, 0))

    lbl_pw1 = ttk.Label(col_pw1)
    lbl_pw1.pack(anchor="w")
    entry_pw1 = ttk.Entry(col_pw1)
    entry_pw1.pack(fill="x")

    lbl_pw2 = ttk.Label(col_pw2)
    lbl_pw2.pack(anchor="w")
    entry_pw2 = ttk.Entry(col_pw2)
    entry_pw2.pack(fill="x")

    lbl_pw3 = ttk.Label(col_pw3)
    lbl_pw3.pack(anchor="w")
    entry_pw3 = ttk.Entry(col_pw3)
    entry_pw3.pack(fill="x")

    # Intervalo de Senha (antes do Re-Host)
    lbl_interval = ttk.Label(frame)
    lbl_interval.pack(anchor="w")

    entry_interval = ttk.Entry(frame)
    entry_interval.insert(0, "1")
    entry_interval.pack(fill="x", pady=(0, 12))

    # Linha Re-Host
    lbl_rehost = ttk.Label(frame)
    lbl_rehost.pack(anchor="w")

    entry_rehost = ttk.Entry(frame)
    entry_rehost.pack(fill="x", pady=(0, 12))

    # Linha do Meio (Idioma + Resolução)
    row_middle = ttk.Frame(frame)
    row_middle.pack(fill="x")

    col_lang = ttk.Frame(row_middle)
    col_lang.pack(side="left", fill="x", expand=True)

    col_resolution = ttk.Frame(row_middle)
    col_resolution.pack(side="left", fill="x", expand=True, padx=(10, 0))

    lbl_language = ttk.Label(col_lang)
    lbl_language.pack(anchor="w")

    language_var = tk.StringVar(value="Português (Brasil)")
    combo_language = ttk.Combobox(
        col_lang, textvariable=language_var, state="readonly", values=list(LANGUAGES.keys())
    )
    combo_language.pack(fill="x")

    # Vincula o evento de mudança de idioma à função de atualização
    combo_language.bind("<<ComboboxSelected>>", atualizar_interface_idioma)

    lbl_resolution = ttk.Label(col_resolution)
    lbl_resolution.pack(anchor="w")

    resolution_var = tk.StringVar(value="1920x1080")
    combo_resolution = ttk.Combobox(
        col_resolution, textvariable=resolution_var, state="readonly", values=list(RESOLUTIONS.keys())
    )
    combo_resolution.pack(fill="x")

    # Checkboxes
    checkbox_row = ttk.Frame(frame)
    checkbox_row.pack(fill="x", pady=(12, 12))

    crystal_var = tk.BooleanVar()
    chk_crystal = ttk.Checkbutton(checkbox_row, variable=crystal_var)
    chk_crystal.pack(side="left")

    equipment_var = tk.BooleanVar()
    chk_equipment = ttk.Checkbutton(checkbox_row, variable=equipment_var)
    chk_equipment.pack(side="left", padx=(20, 0))

    support_var = tk.BooleanVar()
    chk_support = ttk.Checkbutton(checkbox_row, variable=support_var)
    chk_support.pack(side="left", padx=(20, 0))

    # Botão Iniciar
    btn_start = ttk.Button(frame, command=start)
    btn_start.pack(fill="x", pady=(0, 5))

    # Label do Status de Execução
    label_status = ttk.Label(frame, text="", foreground="gray")
    label_status.pack()

    # Rodapé da janela
    label_footer = ttk.Label(frame, font=("Arial", 10), foreground="black")
    label_footer.pack(side="bottom", pady=(15, 0))

    # Força a primeira carga baseada no idioma padrão (pt-br)
    atualizar_interface_idioma()

    watch_processes()
    root.mainloop()