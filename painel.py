import os
import sys
import threading
import tkinter as tk
import keyboard


STATUS_FILE   = "panel_status.txt"
POLL_INTERVAL = 800   # ms

_last_mtime: float = 0.0

def _watch_esc() -> None:
    keyboard.add_hotkey("esc", lambda: os._exit(0), suppress=False)
    # Mantém a thread viva para o hotkey continuar registrado
    threading.Event().wait()

def read_status() -> tuple[str, str, str] | None:
    global _last_mtime
    try:
        mtime = os.path.getmtime(STATUS_FILE)
        if mtime == _last_mtime:
            return None
        _last_mtime = mtime

        with open(STATUS_FILE, "r") as f:
            lines = f.read().splitlines()

        if len(lines) >= 3:
            return lines[0].strip(), lines[1].strip(), lines[2].strip()
    except Exception:
        pass
    return None

def poll() -> None:
    result = read_status()
    if result:
        partidas, max_rehost, ciclos = result
        label_rehost.config(text=f"re-host = {partidas}/{max_rehost}")
        label_ciclos.config(text=f"ciclos  = {ciclos}")
    elif not os.path.exists(STATUS_FILE):
        label_rehost.config(text="re-host = --/--")
        label_ciclos.config(text="ciclos  = --")

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

    root = tk.Tk()
    root.title("Painel Overlay")
    root.overrideredirect(True)
    root.wm_attributes("-topmost", True)
    root.wm_attributes("-alpha", 0.80)
    root.configure(bg="black")

    largura, altura = 170, 55
    pos_x = root.winfo_screenwidth() - largura - 20
    root.geometry(f"{largura}x{altura}+{pos_x}+20")

    FONT  = ("Consolas", 11, "bold")
    COLOR = "#00FF00"

    label_rehost = tk.Label(root, text="re-host = 0/0", fg=COLOR, bg="black",
                            font=FONT, anchor="w")
    label_rehost.pack(fill="x", padx=10, pady=(5, 0))

    label_ciclos = tk.Label(root, text="ciclos  = 0", fg=COLOR, bg="black",
                            font=FONT, anchor="w")
    label_ciclos.pack(fill="x", padx=10, pady=(0, 5))

    root.update()
    make_click_through(root)

    poll()
    root.mainloop()