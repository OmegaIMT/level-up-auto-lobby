import os
import sys
import shutil
import subprocess
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

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


def _cleanup_old_update_files() -> None:
    """updater.py não consegue sobrescrever start.exe/_internal em uso
    durante o próprio update (Windows tranca arquivo/DLL do processo
    rodando) — ele renomeia o antigo pra <nome>.old e troca o novo no
    lugar. Limpa esse resíduo aqui, já que agora (já reiniciado) ninguém
    mais usa ele."""
    for entry in os.listdir("."):
        if entry.endswith(".old"):
            try:
                shutil.rmtree(entry) if os.path.isdir(entry) else os.remove(entry)
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
    "3440x1440": "3440x1440",
}

LANGUAGES_REVERSE = {v: k for k, v in LANGUAGES.items()}
TEXT = {}

# Painel "Vender": rank do item (ícone, não texto) -> vende equipamento/wings
# desse rank quando aparecer. Nomes das variáveis = nome do rank. Ordem de
# pior pra melhor rank: B, A, S, SS, SSS, EX.
RANKS = ["b", "a", "s", "ss", "sss", "ex"]
BUTTON_IMG_DIR = os.path.join("language", "global", "1920x1080", "buttons")
_rank_icons: dict[str, ImageTk.PhotoImage] = {}
_endless_icon: ImageTk.PhotoImage | None = None

def load_rank_icons(canvas_size: int = 44) -> None:
    """Cola o ícone no tamanho nativo (sem redimensionar) num canvas
    transparente fixo - fica nítido em vez de borrado pelo resize pra baixo."""
    for rank in RANKS:
        path = os.path.join(BUTTON_IMG_DIR, f"{rank}.png")
        if not os.path.exists(path):
            continue
        img = Image.open(path).convert("RGBA")
        if img.width > canvas_size or img.height > canvas_size:
            img.thumbnail((canvas_size, canvas_size), Image.LANCZOS)
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        canvas.paste(img, ((canvas_size - img.width) // 2, (canvas_size - img.height) // 2), img)
        _rank_icons[rank] = ImageTk.PhotoImage(canvas)

def load_endless_icon(max_width: int = 300, max_height: int = 60) -> None:
    global _endless_icon
    path = os.path.join(BUTTON_IMG_DIR, "endless.png")
    if not os.path.exists(path):
        return
    img = Image.open(path).convert("RGBA")
    if img.width > max_width or img.height > max_height:
        img.thumbnail((max_width, max_height), Image.LANCZOS)
    _endless_icon = ImageTk.PhotoImage(img)

SELECTED_BG = "#4a90d9"  # cor única de destaque pra todo rank marcado (padronizado)

def build_rank_row(parent: ttk.Frame) -> dict[str, tk.BooleanVar]:
    """tk.Checkbutton nativo aqui saía com um círculo preto feio (chrome do
    tema do Windows em cima do botão) - Label + clique próprio não sofre
    esse chrome, só o ícone, com um destaque uniforme quando marcado."""
    row = ttk.Frame(parent)
    row.pack(pady=(2, 8))
    idle_bg = row.winfo_toplevel().cget("bg")
    variables: dict[str, tk.BooleanVar] = {}
    for rank in RANKS:
        var = tk.BooleanVar()
        variables[rank] = var
        lbl = tk.Label(row, image=_rank_icons.get(rank), bg=idle_bg, bd=0, padx=3, pady=2)
        lbl.pack(side="left", padx=2)

        def _on_change(*_args, v=var, w=lbl):
            w.config(bg=SELECTED_BG if v.get() else idle_bg)

        var.trace_add("write", _on_change)
        lbl.bind("<Button-1>", lambda _event, v=var: v.set(not v.get()))
    return variables

def build_endless_toggle(parent: ttk.Frame) -> tk.BooleanVar:
    """Mesmo esquema do build_rank_row (Label + clique próprio), só que pra
    um item único (endless.png já é o próprio rótulo, sem ícone + texto)."""
    row = ttk.Frame(parent)
    row.pack(pady=(4, 8))
    idle_bg = row.winfo_toplevel().cget("bg")
    var = tk.BooleanVar()
    lbl = tk.Label(row, image=_endless_icon, bg=idle_bg, bd=0, padx=3, pady=2)
    lbl.pack()

    def _on_change(*_args):
        lbl.config(bg=SELECTED_BG if var.get() else idle_bg)

    var.trace_add("write", _on_change)
    lbl.bind("<Button-1>", lambda _event: var.set(not var.get()))
    return var

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

    entry_filtro.delete(0, "end")
    entry_filtro.insert(0, str(saved.get("filtro", "")))

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
    center_var.set(bool(saved.get("center", False)))
    endless_var.set(bool(saved.get("endless", False)))

    saved_sell_equipment = saved.get("sell_equipment", {})
    for rank, var in sell_equipment_vars.items():
        var.set(bool(saved_sell_equipment.get(rank, False)))

    saved_sell_wings = saved.get("sell_wings", {})
    for rank, var in sell_wings_vars.items():
        var.set(bool(saved_sell_wings.get(rank, False)))

    atualizar_interface_idioma()

def atualizar_interface_idioma(event=None) -> None:
    language_display = language_var.get()
    language_folder = LANGUAGES.get(language_display, "pt-br")

    load_language(language_folder)

    root.title(TEXT.get("title", "Auto Lobby Level Up"))
    lbl_pw1.config(text=TEXT.get("password_1", "Password"))
    lbl_rehost.config(text=TEXT.get("rehost", "Re-Host (Partidas)"))
    lbl_filtro.config(text=TEXT.get("filter", "Filtro"))
    lbl_language.config(text=TEXT.get("language", "Idioma"))
    lbl_resolution.config(text=TEXT.get("resolution", "Resolução"))
    chk_crystal.config(text=TEXT.get("crystal", "Cristal"))
    chk_equipment.config(text=TEXT.get("equipment", "Equipamentos"))
    chk_no_xp.config(text=TEXT.get("no_xp", "Desativar XP"))
    chk_support.config(text=TEXT.get("support", "Suporte"))
    chk_center.config(text=TEXT.get("center", "Centro"))
    vender_frame.config(text=TEXT.get("sell", "Vender"))
    bonus_frame.config(text=TEXT.get("bonus", "Bonus"))
    lbl_sell_equipment.config(text=TEXT.get("sell_equipment", "Equipamento"))
    lbl_sell_wings.config(text=TEXT.get("sell_wings", "Wings"))
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
        # Popen (sem esperar) em vez de run: os alvos sobrevivem ao pai no
        # Windows, não precisa bloquear pra eles morrerem. Um taskkill só
        # com múltiplos /IM em vez de um por processo elimina overhead de
        # spawn repetido — reduz bastante o delay até fechar tudo.
        try:
            args = ["taskkill", "/F"]
            for target in ("lobby.exe", "in_game.exe", "fim_game.exe", "painel.exe"):
                args += ["/IM", target]
            subprocess.Popen(args, startupinfo=HIDDEN_WINDOW,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        # wmic foi removido do Windows 11 (24H2+) — kill por commandline
        # (pega lobby.py/in_game.py/fim_game.py/painel.py rodando soltos,
        # ex: respawn feito pelo próprio in_game.py fora do controle deste
        # processo) agora via Get-CimInstance, sucessor suportado.
        ps_script = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
            "Where-Object { $_.CommandLine -match 'lobby\\.py|in_game\\.py|fim_game\\.py|painel\\.py' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                startupinfo=HIDDEN_WINDOW,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

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
    filtro = entry_filtro.get().strip()

    if not rehost.isdigit() or int(rehost) < 1:
        label_status.config(text=TEXT.get("error_rehost", "Error"), foreground="red")
        return

    language_display = language_var.get()
    language_folder = LANGUAGES.get(language_display, "pt-br")
    resolution = resolution_var.get()

    config = {
        "passwords": pw1,
        "filtro": filtro,
        "rehost_max": int(rehost) if rehost.isdigit() else 1,
        "partidas_concluidas": 0,
        "ciclos": 0,
        "language": language_folder,
        "resolution": resolution,
        "crystal": crystal_var.get(),
        "equipment": equipment_var.get(),
        "no_xp": no_xp_var.get(),
        "support": support_var.get(),
        "center": center_var.get(),
        "endless": endless_var.get(),
        "sell_equipment": {rank: var.get() for rank, var in sell_equipment_vars.items()},
        "sell_wings": {rank: var.get() for rank, var in sell_wings_vars.items()},
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
        progress_cb=lambda stage, percent=None: update_queue.put((stage, percent)),
        confirm_cb=_confirm_update,
    )

    if resultado.updated:
        print(f"Atualizado para versão {resultado.remote_version} (arquivos: {resultado.updated_files})")
        # start.exe rodando é o binário antigo (troca por rename só vale pro
        # próximo processo que abrir esse caminho) - reinicia sozinho pra já
        # rodar o binário novo, em vez de depender do usuário fechar/abrir.
        update_queue.put(("restart", None))
    elif resultado.error:
        print(f"Update check: {resultado.error}")

def _confirm_update(remote_version: str, local_version: str) -> bool:
    """
    Chamado pela thread do updater quando acha versão nova. messagebox só
    pode rodar na thread principal do Tkinter, então agenda via root.after e
    bloqueia a thread do updater (threading.Event) até o usuário responder.
    """
    result_holder: dict[str, bool] = {}
    answered = threading.Event()

    def _ask() -> None:
        msg = TEXT.get("update_confirm_msg", "Nova atualização disponível ({version}). Deseja baixar agora?").format(version=remote_version)
        result_holder["answer"] = messagebox.askyesno(
            TEXT.get("update_confirm_title", "Atualização disponível"),
            msg,
        )
        answered.set()

    root.after(0, _ask)
    answered.wait()
    return result_holder.get("answer", False)


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
    elif stage in ("updated", "up_to_date", "declined", "error"):
        progress_bar.stop()
        progress_bar["mode"] = "determinate"
        progress_bar.pack_forget()
        progress_bar["value"] = 0
        label_status.config(text="")
    elif stage == "restart":
        # Só reinicia sozinho se o bot ainda não foi iniciado - se
        # lobby/painel já estão rodando, não interrompe a automação em
        # andamento (o binário novo passa a valer no próximo start manual).
        if processo_lobby is None and processo_painel is None:
            label_status.config(text=TEXT.get("status_update_restart", "Atualizado! Reiniciando..."), foreground="green")
            root.after(1200, _restart_app)

def _restart_app() -> None:
    try:
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable])
        else:
            subprocess.Popen([sys.executable, os.path.abspath(__file__)])
    except Exception:
        pass
    root.destroy()
    os._exit(0)

def run_update_check_async() -> None:
    threading.Thread(target=_update_worker, daemon=True).start()
    root.after(100, _poll_update_queue)

# ==================================================
# UI INITIALIZATION
# ==================================================
if __name__ == "__main__":
    _cleanup_old_update_files()

    root = tk.Tk()
    root.geometry("700x320")
    root.resizable(False, False)

    if os.path.exists("level-up.ico"):
        try: root.iconbitmap("level-up.ico")
        except Exception: pass

    root.protocol("WM_DELETE_WINDOW", on_close)
    load_rank_icons()
    load_endless_icon()

    content = ttk.Frame(root, padding=15)
    content.pack(fill="both", expand=True)

    frame = ttk.Frame(content)
    frame.pack(side="left", fill="both", expand=True)

    # Campo de Senha
    row_passwords = ttk.Frame(frame)
    row_passwords.pack(fill="x", pady=(0, 10))
    lbl_pw1 = ttk.Label(row_passwords)
    lbl_pw1.pack(anchor="w")
    entry_pw1 = ttk.Entry(row_passwords)
    entry_pw1.pack(fill="x")

    # Linha Re-Host + Filtro (lado a lado, metade cada)
    row_rehost_filtro = ttk.Frame(frame)
    row_rehost_filtro.pack(fill="x", pady=(0, 10))

    col_rehost = ttk.Frame(row_rehost_filtro)
    col_rehost.pack(side="left", fill="x", expand=True)
    lbl_rehost = ttk.Label(col_rehost)
    lbl_rehost.pack(anchor="w")
    entry_rehost = ttk.Entry(col_rehost)
    entry_rehost.pack(fill="x")

    col_filtro = ttk.Frame(row_rehost_filtro)
    col_filtro.pack(side="left", fill="x", expand=True, padx=(10, 0))
    lbl_filtro = ttk.Label(col_filtro)
    lbl_filtro.pack(anchor="w")
    entry_filtro = ttk.Entry(col_filtro)
    entry_filtro.pack(fill="x")

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
    center_var = tk.BooleanVar()
    chk_center = ttk.Checkbutton(checkbox_row_2, variable=center_var)
    chk_center.pack(side="left", padx=(20, 0))

    # Coluna direita: painel "Vender" (rank de equipamento/wings a vender) em
    # cima, painel "Bonus" (toggle endless) embaixo - bordas finas, style
    # próprio, mais discretas que o LabelFrame padrão do tema.
    right_style = ttk.Style()
    right_style.configure("Vender.TLabelframe", borderwidth=1)
    right_column = ttk.Frame(content)
    right_column.pack(side="left", fill="y", padx=(15, 0))

    vender_frame = ttk.LabelFrame(right_column, labelanchor="n", style="Vender.TLabelframe")
    vender_frame.pack(side="top", fill="x")

    lbl_sell_equipment = ttk.Label(vender_frame, anchor="center")
    lbl_sell_equipment.pack(fill="x", pady=(10, 0), padx=10)
    sell_equipment_vars = build_rank_row(vender_frame)

    lbl_sell_wings = ttk.Label(vender_frame, anchor="center")
    lbl_sell_wings.pack(fill="x", pady=(4, 8), padx=10)
    sell_wings_vars = build_rank_row(vender_frame)

    bonus_frame = ttk.LabelFrame(right_column, labelanchor="n", style="Vender.TLabelframe")
    bonus_frame.pack(side="top", fill="x", pady=(8, 0))
    endless_var = build_endless_toggle(bonus_frame)

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