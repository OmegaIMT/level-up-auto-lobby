import os
import sys
import json
import threading
import tkinter as tk
import keyboard


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


def _watch_esc() -> None:
    keyboard.add_hotkey("esc", lambda: os._exit(0), suppress=False)
    threading.Event().wait()


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


def poll() -> None:
    result = read_status()
    if result:
        render(result)
    elif not os.path.exists(STATUS_FILE):
        no_data = TEXT.get("no_data", "--")
        label_rehost.config(text=f"{TEXT.get('rehost_label', 're-host')} = {no_data}/{no_data}")
        label_ciclos.config(text=f"{TEXT.get('ciclos_label', 'ciclos')}  = {no_data}")

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

    largura, altura = 260, 60
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

    root.update()
    make_click_through(root)

    poll()
    root.mainloop()