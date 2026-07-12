import ctypes
import os
import subprocess
import sys
import json
import threading
import time
import tkinter as tk

VK_ESCAPE = 0x1B
_user32 = ctypes.WinDLL("user32") if sys.platform == "win32" else None

HIDDEN_WINDOW = subprocess.STARTUPINFO()
HIDDEN_WINDOW.dwFlags     |= subprocess.STARTF_USESHOWWINDOW
HIDDEN_WINDOW.wShowWindow  = 0


CONFIG_FILE  = "config.json"   # gerado pelo start.py — usado só para ler o idioma
STATUS_FILE  = "status.json"   # atualizado ao vivo pelo in_game.py
POLL_INTERVAL = 800   # ms

LANGUAGES = {
    "Português (Brasil)": "pt-br",
    "English": "en-us",
    "Русский": "ru",
    "中文": "zh-cn",
}

DEFAULT_LANGUAGE = "pt-br"

TEXT_DEFAULTS = {
    "rehost_label": "re-host",
    "ciclos_label": "ciclos",
    "exit_label": "exit",
    "esc_key": "esc",
}

TEXT: dict = {}

_last_status_mtime: float = 0.0
_last_status: dict = {}


def _load_language() -> str:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("language", DEFAULT_LANGUAGE)
        except Exception:
            pass
    return DEFAULT_LANGUAGE


def load_panel_texts(language_folder: str) -> None:
    global TEXT
    TEXT = dict(TEXT_DEFAULTS)
    path = os.path.join("language", language_folder, "painel.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            dados = json.load(f)
            if isinstance(dados, dict):
                TEXT.update(dados)
    except Exception as e:
        print(f"Erro ao carregar painel.json ({language_folder}): {e}")


def ensure_status_file() -> None:
    """Gera status.json com valores default se o arquivo ainda não existir."""
    if os.path.exists(STATUS_FILE):
        return
    default = {"partidas": 0, "rehost_max": 0, "ciclos": 0}
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _matar_irmaos() -> None:
    """
    Esc em qualquer um dos três (lobby/in_game/painel) derruba os três.
    Pula o próprio .exe na lista: taskkill mata a própria imagem na hora
    (processo some no meio do for), o que abortaria antes de matar os
    outros - o próprio processo já se encerra sozinho com os._exit depois.
    """
    if sys.platform != "win32":
        return
    exe_proprio = os.path.basename(sys.executable).lower() if getattr(sys, "frozen", False) else None
    alvos = [t for t in ("lobby.exe", "in_game.exe", "fim_game.exe", "painel.exe") if t != exe_proprio]

    if alvos:
        try:
            args = ["taskkill", "/F"]
            for t in alvos:
                args += ["/IM", t]
            subprocess.Popen(args, startupinfo=HIDDEN_WINDOW,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    ps_script = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
        "Where-Object { $_.CommandLine -match 'lobby\\.py|in_game\\.py|fim_game\\.py|painel\\.py' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                          startupinfo=HIDDEN_WINDOW,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _watch_esc() -> None:
    """
    Poll de VK_ESCAPE via GetAsyncKeyState em vez de biblioteca 'keyboard':
    hotkeys por nome dela dependem do layout de teclado ativo e falham em
    layouts não-US (ex: russo/ЙЦУКЕН) - VK code é sempre o mesmo, layout
    não importa.
    """
    if _user32 is None:
        return
    while True:
        if _user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
            _matar_irmaos()
            os._exit(0)
        time.sleep(0.05)


def read_status() -> dict | None:
    global _last_status_mtime, _last_status
    try:
        mtime = os.path.getmtime(STATUS_FILE)
        if mtime == _last_status_mtime:
            return None
        _last_status_mtime = mtime

        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            _last_status = data
            return data
    except Exception:
        pass
    return None


def render(status: dict) -> None:
    partidas   = status.get("partidas", 0)
    rehost_max = status.get("rehost_max", 0)
    ciclos     = status.get("ciclos", 0)

    label_rehost.config(text=f"{TEXT.get('rehost_label', 're-host')} = {partidas}/{rehost_max}")
    label_ciclos.config(text=f"{TEXT.get('ciclos_label', 'ciclos')}  = {ciclos}")
    label_exit.config(text=f"{TEXT.get('exit_label', 'exit')}  = {TEXT.get('esc_key', 'esc')}")


def poll() -> None:
    result = read_status()
    if result:
        render(result)
    elif not os.path.exists(STATUS_FILE):
        no_data = TEXT.get("no_data", "--")
        label_rehost.config(text=f"{TEXT.get('rehost_label', 're-host')} = {no_data}/{no_data}")
        label_ciclos.config(text=f"{TEXT.get('ciclos_label', 'ciclos')}  = {no_data}")
        label_exit.config(text=f"{TEXT.get('exit_label', 'exit')}  = {TEXT.get('esc_key', 'esc')}")

    root.after(POLL_INTERVAL, poll)


def make_click_through(window: tk.Tk) -> None:
    if sys.platform != "win32":
        return
    import ctypes
    GWL_EXSTYLE       = -20
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_LAYERED     = 0x00080000

    user32 = ctypes.windll.user32
    hwnd   = user32.GetParent(window.winfo_id())
    style  = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED)


if __name__ == "__main__":
    threading.Thread(target=_watch_esc, daemon=True).start()

    ensure_status_file()

    language_folder = _load_language()
    load_panel_texts(language_folder)

    root = tk.Tk()
    root.title("Painel Overlay")
    root.overrideredirect(True)
    root.wm_attributes("-topmost", True)
    root.wm_attributes("-alpha", 0.80)
    root.configure(bg="black")

    largura, altura = 260, 80
    pos_x = root.winfo_screenwidth() - largura - 20
    root.geometry(f"{largura}x{altura}+{pos_x}+20")

    FONT  = ("Consolas", 11, "bold")
    COLOR = "#00FF00"

    label_rehost = tk.Label(root, text="re-host = 0/0", fg=COLOR, bg="black",
                            font=FONT, anchor="w")
    label_rehost.pack(fill="x", padx=10, pady=(5, 0))

    label_ciclos = tk.Label(root, text="ciclos  = 0", fg=COLOR, bg="black",
                            font=FONT, anchor="w")
    label_ciclos.pack(fill="x", padx=10, pady=(0, 0))

    label_exit = tk.Label(root, text="exit  = esc", fg=COLOR, bg="black",
                          font=FONT, anchor="w")
    label_exit.pack(fill="x", padx=10, pady=(0, 5))

    root.update()
    make_click_through(root)

    poll()
    root.mainloop()