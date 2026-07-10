import os
import sys
import shutil
import subprocess
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk

import updater

# ==================================================
# HIDE CONSOLE
# ==================================================
if sys.platform == "win32":
    import ctypes
    hWnd = ctypes.WinDLL("kernel32").GetConsoleWindow()
    if hWnd:
        ctypes.WinDLL("user32").ShowWindow(hWnd, 0)

HIDDEN_WINDOW = subprocess.STARTUPINFO()
HIDDEN_WINDOW.dwFlags |= subprocess.STARTF_USESHOWWINDOW
HIDDEN_WINDOW.wShowWindow = 0

STATUS_FILE = "status.json"
CONFIG_FILE = "config.json"

processo_lobby = None
processo_painel = None


def _find_python_cmd() -> list[str]:
    """Comando pra rodar um .py (lobby.py/painel.py).

    Quando start.py roda congelado como start.exe, sys.executable aponta
    pro próprio start.exe — não é um interpretador python de verdade, então
    `Popen([sys.executable, "lobby.py"])` só reabriria outro start.exe.
    Isso só importa aqui: lobby.py/painel.py sempre rodam soltos (nunca
    congelados), então o sys.executable deles já é o python real.
    """
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    for candidate in ("pythonw.exe", "python.exe"):
        path = shutil.which(candidate)
        if path:
            return [path]
    py_launcher = shutil.which("py")
    if py_launcher:
        return [py_launcher, "-3"]
    return ["python"]


PYTHON_CMD = _find_python_cmd()


def _cleanup_old_exe() -> None:
    """updater.py não consegue sobrescrever start.exe em uso durante o
    próprio update (Windows tranca o arquivo do processo rodando) — ele
    renomeia o antigo pra start.exe.old e troca o novo no lugar. Limpa
    esse resíduo aqui, já que agora (com start.exe já trocado) ninguém
    mais usa ele."""
    old_path = "start.exe.old"
    if os.path.exists(old_path):
        try:
            os.remove(old_path)
        except Exception:
            pass

# ==================================================
# CONFIGURATIONS & LANGUAGES
# ==================================================
LANGUAGES = {
    "Português (Brasil)": "pt-br",
    "English": "en-us",
    "Русский": "ru",
    "中文": "zh-cn",
}

RESOLUTIONS = {
    "1920x1080": "1920x1080",
    "1600x900": "1600x900",
}

LANGUAGES_REVERSE = {v: k for k, v in LANGUAGES.items()}
TEXT = {}

def load_language(language_folder: str) -> None:
    global TEXT
    path = os.path.join("language", language_folder, "start.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            dados = json.load(f)
            if isinstance(dados, dict):
                TEXT.update(dados)
    except Exception as e:
        print(f"Erro ao carregar idioma {language_folder}: {e}")

def load_saved_config() -> dict | None:
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"Erro ao carregar config salva: {e}")
        return None

def apply_saved_config(saved: dict) -> None:
    password_data = saved.get("passwords", "")
    entry_pw1.delete(0, "end")
    if isinstance(password_data, list):
        if password_data: entry_pw1.insert(0, str(password_data[0]))
    else:
        entry_pw1.insert(0, str(password_data))

    entry_rehost.delete(0, "end")
    entry_rehost.insert(0, str(saved.get("rehost_max", 1)))

    saved_language_folder = saved.get("language", "pt-br")
    saved_language_display = LANGUAGES_REVERSE.get(saved_language_folder)
    if saved_language_display:
        language_var.set(saved_language_display)

    saved_resolution = saved.get("resolution")
    if saved_resolution in RESOLUTIONS:
        resolution_var.set(saved_resolution)

    crystal_var.set(bool(saved.get("crystal", False)))
    equipment_var.set(bool(saved.get("equipment", False)))
    no_xp_var.set(bool(saved.get("no_xp", False)))
    support_var.set(bool(saved.get("support", False)))

    atualizar_interface_idioma()

def atualizar_interface_idioma(event=None) -> None:
    language_display = language_var.get()
    language_folder = LANGUAGES.get(language_display, "pt-br")

    load_language(language_folder)

    root.title(TEXT.get("title", "Auto Lobby Level Up"))
    lbl_pw1.config(text=TEXT.get("password_1", "Password"))
    lbl_rehost.config(text=TEXT.get("rehost", "Re-Host (Partidas)"))
    lbl_language.config(text=TEXT.get("language", "Idioma"))
    lbl_resolution.config(text=TEXT.get("resolution", "Resolução"))
    chk_crystal.config(text=TEXT.get("crystal", "Cristal"))
    chk_equipment.config(text=TEXT.get("equipment", "Equipamentos"))
    chk_no_xp.config(text=TEXT.get("no_xp", "Desativar XP"))
    chk_support.config(text=TEXT.get("support", "Suporte"))
    btn_start.config(text=TEXT.get("start", "Start"))
    label_footer.config(text=TEXT.get("footer", ""))

    label_status.config(text="")

# ==================================================
# HELPERS / ACTIONS
# ==================================================
def save_status(partidas: int, rehost_max: int, ciclos: int, current_pw: str = "") -> None:
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
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar config: {e}")

def kill_all_children() -> None:
    global processo_lobby, processo_painel
    for proc in (processo_lobby, processo_painel):
        if proc and proc.poll() is None:
            try: proc.terminate()
            except Exception: pass

    if sys.platform == "win32":
        for target in ["lobby.exe", "in_game.exe", "painel.exe"]:
            os.system(f'taskkill /f /im {target} >nul 2>&1')
        for script in ["lobby.py", "in_game.py", "painel.py"]:
            os.system(f'wmic process where "commandline like \'%{script}%\'" delete >nul 2>&1')

def on_close() -> None:
    kill_all_children()
    root.destroy()
    os._exit(0)

def start() -> None:
    global processo_lobby, processo_painel
    if processo_lobby and processo_lobby.poll() is None:
        return

    pw1 = entry_pw1.get().strip()
    rehost = entry_rehost.get().strip() or "1"

    if not rehost.isdigit() or int(rehost) < 1:
        label_status.config(text=TEXT.get("error_rehost", "Error"), foreground="red")
        return

    language_display = language_var.get()
    language_folder = LANGUAGES.get(language_display, "pt-br")
    resolution = resolution_var.get()

    config = {
        "passwords": pw1,
        "rehost_max": int(rehost) if rehost.isdigit() else 1,
        "partidas_concluidas": 0,
        "ciclos": 0,
        "language": language_folder,
        "resolution": resolution,
        "crystal": crystal_var.get(),
        "equipment": equipment_var.get(),
        "no_xp": no_xp_var.get(),
        "support": support_var.get(),
    }

    save_config(config)
    save_status(0, int(rehost) if rehost.isdigit() else 1, 0, current_pw=pw1)

    if os.path.exists("lobby.exe"):
        processo_lobby = subprocess.Popen(["lobby.exe", CONFIG_FILE], startupinfo=HIDDEN_WINDOW)
    else:
        processo_lobby = subprocess.Popen([*PYTHON_CMD, "lobby.py", CONFIG_FILE], startupinfo=HIDDEN_WINDOW)

    if os.path.exists("painel.exe"):
        processo_painel = subprocess.Popen(["painel.exe"], startupinfo=HIDDEN_WINDOW)
    else:
        processo_painel = subprocess.Popen([*PYTHON_CMD, "painel.py"], startupinfo=HIDDEN_WINDOW)

    status_msg = TEXT.get("status_started", "Iniciado")
    label_status.config(text=f"{status_msg} ({language_folder})", foreground="green")
    root.after(1200, root.iconify)

# ==================================================
# AUTO-UPDATE (Release) — roda em background depois que a UI já existe, pra
# poder mostrar status/progresso sem travar a janela.
# ==================================================
update_queue: "queue.Queue[tuple[str, int | None]]" = queue.Queue()

def _update_worker() -> None:
    """
    Compara o version.json local com o da branch main no GitHub. Se houver
    versão nova, baixa o asset .zip da Release mais recente (build já
    compilado com todos os .exe) e sobrescreve tudo. lobby.exe/in_game.exe/
    painel.exe são trocados na hora; start.exe (em uso pelo processo atual)
    só vale a partir do próximo start.
    Falhas de rede são silenciosas — o app sempre abre normalmente.
    Roda em thread separada; só empilha eventos na fila (Tkinter não é
    thread-safe pra mexer em widget direto daqui).
    """
    resultado = updater.check_for_updates(
        progress_cb=lambda stage, percent=None: update_queue.put((stage, percent))
    )

    if resultado.updated:
        print(f"Atualizado para versão {resultado.remote_version} (arquivos: {resultado.updated_files})")
    elif resultado.error:
        print(f"Update check: {resultado.error}")

def _poll_update_queue() -> None:
    try:
        while True:
            stage, percent = update_queue.get_nowait()
            _apply_update_stage(stage, percent)
    except queue.Empty:
        pass
    root.after(100, _poll_update_queue)

def _apply_update_stage(stage: str, percent: int | None) -> None:
    if stage == "checking":
        label_status.config(text=TEXT.get("status_checking_update", "Buscando atualização..."), foreground="gray")
    elif stage == "found":
        label_status.config(text=TEXT.get("status_update_found", "Atualização encontrada"), foreground="gray")
    elif stage == "downloading":
        label_status.config(text=TEXT.get("status_downloading_update", "Baixando atualização..."), foreground="gray")
        if not progress_bar.winfo_ismapped():
            progress_bar.pack(fill="x", pady=(0, 5), before=label_footer)
        if percent is None:
            # GitHub manda o zip sem Content-Length — sem % pra calcular,
            # mostra indeterminado em vez de travar em 0.
            if progress_bar["mode"] != "indeterminate":
                progress_bar["mode"] = "indeterminate"
                progress_bar.start(15)
        else:
            if progress_bar["mode"] != "determinate":
                progress_bar.stop()
                progress_bar["mode"] = "determinate"
            progress_bar["value"] = percent
    elif stage in ("updated", "up_to_date", "error"):
        progress_bar.stop()
        progress_bar["mode"] = "determinate"
        progress_bar.pack_forget()
        progress_bar["value"] = 0
        label_status.config(text="")

def run_update_check_async() -> None:
    threading.Thread(target=_update_worker, daemon=True).start()
    root.after(100, _poll_update_queue)

# ==================================================
# UI INITIALIZATION
# ==================================================
if __name__ == "__main__":
    _cleanup_old_exe()

    root = tk.Tk()
    root.geometry("350x320")
    root.resizable(False, False)

    if os.path.exists("level-up.ico"):
        try: root.iconbitmap("level-up.ico")
        except Exception: pass

    root.protocol("WM_DELETE_WINDOW", on_close)
    frame = ttk.Frame(root, padding=15)
    frame.pack(fill="both", expand=True)

    # Campo de Senha
    row_passwords = ttk.Frame(frame)
    row_passwords.pack(fill="x", pady=(0, 10))
    lbl_pw1 = ttk.Label(row_passwords)
    lbl_pw1.pack(anchor="w")
    entry_pw1 = ttk.Entry(row_passwords)
    entry_pw1.pack(fill="x")

    # Campo de Re-Host
    lbl_rehost = ttk.Label(frame)
    lbl_rehost.pack(anchor="w")
    entry_rehost = ttk.Entry(frame)
    entry_rehost.pack(fill="x", pady=(0, 10))

    # Linha do Meio (Idioma + Resolução)
    row_middle = ttk.Frame(frame)
    row_middle.pack(fill="x", pady=(0, 0))

    col_lang = ttk.Frame(row_middle)
    col_lang.pack(side="left", fill="x", expand=True)
    lbl_language = ttk.Label(col_lang)
    lbl_language.pack(anchor="w")
    language_var = tk.StringVar(value="Português (Brasil)")
    combo_language = ttk.Combobox(col_lang, textvariable=language_var, state="readonly", values=list(LANGUAGES.keys()))
    combo_language.pack(fill="x")
    combo_language.bind("<<ComboboxSelected>>", atualizar_interface_idioma)

    col_resolution = ttk.Frame(row_middle)
    col_resolution.pack(side="left", fill="x", expand=True, padx=(10, 0))
    lbl_resolution = ttk.Label(col_resolution)
    lbl_resolution.pack(anchor="w")
    resolution_var = tk.StringVar(value="1920x1080")
    combo_resolution = ttk.Combobox(col_resolution, textvariable=resolution_var, state="readonly", values=list(RESOLUTIONS.keys()))
    combo_resolution.pack(fill="x")

    # Checkboxes (3: Cristal, Equipamentos, Desativar XP)
    checkbox_row = ttk.Frame(frame)
    checkbox_row.pack(fill="x", pady=(12, 12))
    crystal_var = tk.BooleanVar()
    chk_crystal = ttk.Checkbutton(checkbox_row, variable=crystal_var)
    chk_crystal.pack(side="left")
    equipment_var = tk.BooleanVar()
    chk_equipment = ttk.Checkbutton(checkbox_row, variable=equipment_var)
    chk_equipment.pack(side="left", padx=(20, 0))
    no_xp_var = tk.BooleanVar()
    chk_no_xp = ttk.Checkbutton(checkbox_row, variable=no_xp_var)
    chk_no_xp.pack(side="left", padx=(20, 0))

    # Linha separada para "Support" (evita espremer o layout de 350px)
    checkbox_row_2 = ttk.Frame(frame)
    checkbox_row_2.pack(fill="x", pady=(0, 12))
    support_var = tk.BooleanVar()
    chk_support = ttk.Checkbutton(checkbox_row_2, variable=support_var)
    chk_support.pack(side="left")

    # Botões e Status
    btn_start = ttk.Button(frame, command=start)
    btn_start.pack(fill="x", pady=(0, 5))
    label_status = ttk.Label(frame, text="", foreground="gray")
    label_status.pack()
    # Barra de progresso do auto-update — só aparece durante o download
    # (ver _apply_update_stage). Fica entre o Start e o rodapé.
    progress_bar = ttk.Progressbar(frame, orient="horizontal", mode="determinate", maximum=100)
    label_footer = ttk.Label(frame, font=("Arial", 9), foreground="black")
    label_footer.pack(side="bottom", pady=(5, 0))

    # Inicialização padrão da UI
    atualizar_interface_idioma()

    saved_config = load_saved_config()
    if saved_config:
        apply_saved_config(saved_config)

    run_update_check_async()
    root.mainloop()