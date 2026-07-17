"""
coord_capture.py — Ferramenta manual (roda à parte, não entra no build) pra
capturar as coordenadas de clique dos fluxos de venda (Wings/Equipamento) e
gerar coords/coords_base_vender.json.

Uso:
    python coord_capture.py

Com o Dota aberto na resolução configurada em config.json, um overlay no
canto da tela mostra qual coordenada capturar agora. Posiciona o mouse em
cima do botão/elemento pedido e:
    F8  = captura a posição atual do mouse e avança
    F9  = pula esta coordenada (fica sem valor, não grava)
    ESC = salva o que já foi capturado e sai

Salva progressivamente (a cada F8) em coords/coords_base_vender.json,
chaveado só pela resolução (Dota não segue a escala de exibição do Windows),
com um bloco por seção (wings/equipamento).
"""
import os
import sys
import json
import ctypes
import tkinter as tk

if sys.platform != "win32":
    print("Só funciona no Windows.")
    sys.exit(1)

user32 = ctypes.WinDLL("user32")
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
except Exception:
    user32.SetProcessDPIAware()

CONFIG_FILE = "config.json"
COORDS_DIR = "coords"
OUT_FILE = os.path.join(COORDS_DIR, "coords_base_vender.json")

VK_F8 = 0x77
VK_F9 = 0x78
VK_ESCAPE = 0x1B


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


CONFIG = load_config()
RESOLUTION = CONFIG.get("resolution", "1920x1080")

# Ordem de captura por seção. "confirm"/"closer" existem nas duas seções
# mas são telas diferentes (loja de wings x forja de equipamento), por isso
# cada seção guarda seu próprio bloco no JSON em vez de reaproveitar a
# mesma chave.
SECTIONS: list[tuple[str, list[str]]] = [
    ("wings", ["wing_shop", "wings", "buy", "wing_b", "wing_a", "wing_s",
               "wing_ss", "wing_sss", "wing_ex", "buy_2", "confirm", "ok", "closer"]),
    ("equipamento", ["equip_forge", "upgrade", "equip_b", "equip_a", "equip_s",
                      "equip_ss", "equip_sss", "equip_ex", "confirm", "closer"]),
    ("endless", ["mapa", "dog"]),
    ("hero", ["hero"]),
]

STEPS: list[tuple[str, str]] = [(secao, chave) for secao, chaves in SECTIONS for chave in chaves]


def load_out_file() -> dict:
    if not os.path.exists(OUT_FILE):
        return {}
    try:
        with open(OUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


RESULT = load_out_file()
RESULT.setdefault(RESOLUTION, {})
for secao, _ in SECTIONS:
    RESULT[RESOLUTION].setdefault(secao, {})


def save_out_file() -> None:
    os.makedirs(COORDS_DIR, exist_ok=True)
    tmp = OUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(RESULT, f, ensure_ascii=False, indent=2)
    os.replace(tmp, OUT_FILE)


def get_cursor_pos() -> tuple[int, int]:
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class Capturador:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.index = 0
        self.f8_held = False
        self.f9_held = False
        self.esc_held = False

        self.label_secao = tk.Label(root, fg="#00FF00", bg="black",
                                     font=("Consolas", 11, "bold"), anchor="w")
        self.label_secao.pack(fill="x", padx=10, pady=(8, 0))

        self.label_chave = tk.Label(root, fg="#FFFFFF", bg="black",
                                     font=("Consolas", 14, "bold"), anchor="w")
        self.label_chave.pack(fill="x", padx=10, pady=(2, 0))

        self.label_progresso = tk.Label(root, fg="#AAAAAA", bg="black",
                                         font=("Consolas", 9), anchor="w")
        self.label_progresso.pack(fill="x", padx=10, pady=(2, 0))

        self.label_ajuda = tk.Label(
            root, fg="#00FF00", bg="black", font=("Consolas", 9), anchor="w",
            text="F8 captura   F9 pula   ESC salva e sai",
        )
        self.label_ajuda.pack(fill="x", padx=10, pady=(6, 8))

        self.render()
        self.poll()

    def render(self) -> None:
        if self.index >= len(STEPS):
            self.label_secao.config(text=f"{RESOLUTION} - concluído")
            self.label_chave.config(text="Tudo capturado!")
            self.label_progresso.config(text="ESC pra sair")
            return
        secao, chave = STEPS[self.index]
        self.label_secao.config(text=f"{RESOLUTION} - {secao}")
        self.label_chave.config(text=chave)
        self.label_progresso.config(text=f"{self.index + 1}/{len(STEPS)}")

    def capturar_atual(self) -> None:
        if self.index >= len(STEPS):
            return
        secao, chave = STEPS[self.index]
        x, y = get_cursor_pos()
        RESULT[RESOLUTION][secao][chave] = [x, y]
        save_out_file()
        self.index += 1
        self.render()

    def pular_atual(self) -> None:
        if self.index >= len(STEPS):
            return
        self.index += 1
        self.render()

    def poll(self) -> None:
        f8 = key_down(VK_F8)
        if f8 and not self.f8_held:
            self.capturar_atual()
        self.f8_held = f8

        f9 = key_down(VK_F9)
        if f9 and not self.f9_held:
            self.pular_atual()
        self.f9_held = f9

        esc = key_down(VK_ESCAPE)
        if esc and not self.esc_held:
            save_out_file()
            self.root.destroy()
            os._exit(0)
        self.esc_held = esc

        self.root.after(30, self.poll)


def make_click_through(window: tk.Tk) -> None:
    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_LAYERED = 0x00080000
    hwnd = user32.GetParent(window.winfo_id())
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED)


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Coord Capture")
    root.overrideredirect(True)
    root.wm_attributes("-topmost", True)
    root.wm_attributes("-alpha", 0.85)
    root.configure(bg="black")

    largura, altura = 280, 130
    pos_x = root.winfo_screenwidth() - largura - 20
    root.geometry(f"{largura}x{altura}+{pos_x}+20")

    Capturador(root)

    root.update()
    make_click_through(root)

    root.mainloop()
