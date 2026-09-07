"""
resumo.py — Janela de resumo da sessão, mostrada quando o usuário aperta ESC
pra encerrar o bot (lobby.py/in_game.py/fim_game.py/painel.py sobem esse
processo antes de se matarem - ver _launch_resumo em cada um deles).

Lê stats.json (contadores de sessão, zerados só quando clica Iniciar no
start.py - ver start.py/reset_stats) + config.json (ciclos) e mostra os
números formatados. Fecha com ESC (mesma tecla que abriu o encerramento).
"""
import ctypes
import json
import os
import sys
import threading
import time
import tkinter as tk

if sys.platform == "win32":
    _hwnd_console = ctypes.WinDLL("kernel32").GetConsoleWindow()
    if _hwnd_console:
        ctypes.WinDLL("user32").ShowWindow(_hwnd_console, 0)

VK_ESCAPE = 0x1B
_user32 = ctypes.WinDLL("user32") if sys.platform == "win32" else None

CONFIG_FILE = "config.json"
STATS_FILE = "stats.json"
DEFAULT_LANGUAGE = "pt-br"

TEXT_DEFAULTS = {
    "titulo": "Resumo da sessão",
    "partidas_label": "partidas jogadas",
    "ciclos_label": "ciclos completos",
    "salas_achadas_label": "salas achadas",
    "salas_conectadas_label": "salas conectadas",
    "erros_conexao_label": "erros de conexão",
    "encerrados_por_erro_label": "ciclos encerrados por erro",
    "tempo_buscando_sala_label": "tempo buscando sala",
    "tempo_em_partida_label": "tempo total em partida",
    "tempo_medio_partida_label": "tempo médio por partida",
    "tempo_ligado_label": "tempo total ligado",
    "fechar_label": "ESC = fechar",
}


def _load_language() -> str:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("language", DEFAULT_LANGUAGE)
        except Exception:
            pass
    return DEFAULT_LANGUAGE


def _load_texts(language_folder: str) -> dict:
    texts = dict(TEXT_DEFAULTS)
    path = os.path.join("language", language_folder, "resumo.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            dados = json.load(f)
            if isinstance(dados, dict):
                texts.update(dados)
    except Exception:
        pass
    return texts


def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _fmt_hms(segundos: float) -> str:
    segundos = max(int(segundos), 0)
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _watch_esc() -> None:
    if _user32 is None:
        return
    while not (_user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000):
        time.sleep(0.05)
    os._exit(0)


def main() -> None:
    texts = _load_texts(_load_language())

    stats = _load_json(STATS_FILE)
    config = _load_json(CONFIG_FILE)

    partidas = stats.get("partidas_total", 0)
    ciclos = config.get("ciclos", 0)
    salas_achadas = stats.get("salas_achadas", 0)
    salas_conectadas = stats.get("salas_conectadas", 0)
    erros_conexao = stats.get("erros_conexao", 0)
    encerrados_por_erro = stats.get("partidas_encerradas_antes_ciclo", 0)
    tempo_buscando_sala = stats.get("tempo_buscando_sala_total", 0.0)
    tempo_em_partida = stats.get("tempo_em_partida_total", 0.0)
    tempo_medio = (tempo_em_partida / partidas) if partidas else 0.0
    bot_started_at = stats.get("bot_started_at", 0.0)
    tempo_ligado = (time.time() - bot_started_at) if bot_started_at else 0.0

    linhas = [
        (texts["partidas_label"], str(partidas)),
        (texts["ciclos_label"], str(ciclos)),
        (texts["salas_achadas_label"], str(salas_achadas)),
        (texts["salas_conectadas_label"], str(salas_conectadas)),
        (texts["erros_conexao_label"], str(erros_conexao)),
        (texts["encerrados_por_erro_label"], str(encerrados_por_erro)),
        (texts["tempo_buscando_sala_label"], _fmt_hms(tempo_buscando_sala)),
        (texts["tempo_em_partida_label"], _fmt_hms(tempo_em_partida)),
        (texts["tempo_medio_partida_label"], _fmt_hms(tempo_medio)),
        (texts["tempo_ligado_label"], _fmt_hms(tempo_ligado)),
    ]

    root = tk.Tk()
    root.title(texts["titulo"])
    root.configure(bg="black")
    root.resizable(False, False)
    root.wm_attributes("-topmost", True)

    if os.path.exists("level-up.ico"):
        try:
            root.iconbitmap("level-up.ico")
        except Exception:
            pass

    LARGURA = 380
    ALTURA = 70 + len(linhas) * 26 + 40
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{LARGURA}x{ALTURA}+{(sw - LARGURA) // 2}+{(sh - ALTURA) // 2}")

    FONT_TITULO = ("Consolas", 13, "bold")
    FONT = ("Consolas", 11, "bold")
    COLOR = "#00FF00"

    tk.Label(root, text=texts["titulo"], fg=COLOR, bg="black", font=FONT_TITULO).pack(pady=(14, 10))

    for label, valor in linhas:
        linha = tk.Frame(root, bg="black")
        linha.pack(fill="x", padx=18, pady=1)
        tk.Label(linha, text=label, fg=COLOR, bg="black", font=FONT, anchor="w").pack(side="left")
        tk.Label(linha, text=valor, fg=COLOR, bg="black", font=FONT, anchor="e").pack(side="right")

    tk.Label(root, text=texts["fechar_label"], fg="#888888", bg="black", font=("Consolas", 9)).pack(pady=(14, 10))

    root.focus_force()
    threading.Thread(target=_watch_esc, daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()
