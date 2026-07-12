import json
import os
import subprocess
import sys
import threading
import time
from typing import Optional

import pyautogui

# ==================================================
# HIDE CONSOLE WINDOW (WINDOWS)
# ==================================================
if sys.platform == "win32":
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32")
    user32 = ctypes.WinDLL("user32")

    # DPI awareness: sem isso, GetSystemMetrics/screenshot usam resolução
    # escalada pelo Windows (ex: 1536x864 em vez de 1920x1080 físico),
    # e os templates de imagem (capturados em pixels reais) nunca batem.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        user32.SetProcessDPIAware()

    hWnd = kernel32.GetConsoleWindow()
    if hWnd:
        user32.ShowWindow(hWnd, 0)

HIDDEN_WINDOW = subprocess.STARTUPINFO()
HIDDEN_WINDOW.dwFlags |= subprocess.STARTF_USESHOWWINDOW
HIDDEN_WINDOW.wShowWindow = 0

# ==================================================
# TIMING CONSTANTS
# ==================================================
POLL_FAST = 0.08  # polling reativo (aguardando aceitar/erro) — 33Hz era exagero pra UI, 12Hz já é bem mais rápido que reação humana e derruba CPU ~3x
POLL_NORMAL = 0.03  # polling padrão do loop de lobby
POLL_ATT = 0.02  # intervalo entre cliques no botão de atualizar
CLICK_PAUSE = 0.03  # pausa antes de cada clique
FOCUS_WAIT = 0.8  # tempo para o Windows processar foco
ATT_CYCLE_WAIT = 0.15  # espera após cada clique em ATT antes de checar
ATT_CYCLE_WAIT_NO_CACHE = 0.4  # espera maior quando game.png ainda não tem coordenada em cache (dá tempo de ver a tela)
MENU_STEP_WAIT = 0.25  # pausa entre cliques no menu (reduzida pela metade)
SAIR_TIMEOUT = 1.5  # timeout do popup opcional "sair" (reduzido pela metade)

# ==================================================
# SESSION CONFIG (gerado pelo start.py)
# ==================================================
SESSION_CONFIG_FILE = sys.argv[1] if len(sys.argv) > 1 else "config.json"
STATUS_FILE = "status.json"  # status ao vivo, lido pelo painel.py
LOCK_FILE = "bot.lock"  # sentinela compartilhado com painel.py

UP_PREFIX = "up-"  # sempre digitado no campo de busca


def _load_session_config() -> dict:
    """Lê o config.json gerado pelo start.py."""
    if os.path.exists(SESSION_CONFIG_FILE):
        try:
            with open(SESSION_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Erro ao ler {SESSION_CONFIG_FILE}: {e}")

    return {
        "passwords": "4433",
        "language": "pt-br",
    }


_status_lock = threading.Lock()


def _read_status_raw() -> dict:
    """Lê o status.json atual do disco, sem cache."""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


_STATUS_DEFAULTS = {
    "partidas": 0,
    "rehost_max": 0,
    "ciclos": 0,
    "current_password": "",
    "password_deadline": 0.0,
    "current_image": "",
    "image_found": False,
}


def save_status(
    partidas: int | None = None,
    rehost_max: int | None = None,
    ciclos: int | None = None,
    current_pw: str | None = None,
    password_deadline: float | None = None,
    current_image: str | None = None,
    image_found: bool | None = None,
) -> None:
    """Atualiza o status.json lido pelo painel.py fazendo MERGE."""
    with _status_lock:
        current = _read_status_raw()
        payload = {**_STATUS_DEFAULTS, **current}

        if partidas is not None:
            payload["partidas"] = partidas
        if rehost_max is not None:
            payload["rehost_max"] = rehost_max
        if ciclos is not None:
            payload["ciclos"] = ciclos
        if current_pw is not None:
            payload["current_password"] = current_pw
        if password_deadline is not None:
            payload["password_deadline"] = password_deadline
        if current_image is not None:
            payload["current_image"] = current_image
        if image_found is not None:
            payload["image_found"] = image_found

        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Erro ao salvar {STATUS_FILE}: {e}")


# Debug ao vivo (painel.py): qual imagem locate() buscou por último e se achou.
# Throttle pra não gerar I/O em disco a cada 30ms do polling normal.
_last_debug: tuple[str, bool] | None = None
_last_debug_time = 0.0
DEBUG_MIN_INTERVAL = 0.15


def _update_debug(name: str, found: bool) -> None:
    global _last_debug, _last_debug_time
    now = time.time()
    if _last_debug == (name, found) and (now - _last_debug_time) < DEBUG_MIN_INTERVAL:
        return
    _last_debug = (name, found)
    _last_debug_time = now
    save_status(current_image=name, image_found=found)


SESSION = _load_session_config()

# Lê a senha única do JSON novo (podendo vir como string/int direto ou lista antiga)
raw_pw = SESSION.get("passwords", "")
if isinstance(raw_pw, list):
    PASSWORD_FIXED = str(raw_pw[0]) if raw_pw else ""
else:
    PASSWORD_FIXED = str(raw_pw)

REHOST_MAX: int = SESSION.get("rehost_max", 1)
LANGUAGE = SESSION.get("language", "pt-br")
RESOLUTION = SESSION.get("resolution", "1920x1080")

_IMG_DIR_WITH_RES = os.path.join("language", LANGUAGE, RESOLUTION, "lobby")
_IMG_DIR_NO_RES = os.path.join("language", LANGUAGE, "lobby")

IMG_DIR = _IMG_DIR_WITH_RES if os.path.exists(_IMG_DIR_WITH_RES) else _IMG_DIR_NO_RES

# coords/: cache de coordenadas (posição da última imagem achada), um
# arquivo por resolução. Dota renderiza em pixels reais, não segue a escala
# de exibição do Windows (100%/125%/...), então a mesma resolução sempre
# cai na mesma coordenada - esse arquivo é versionado (ver build.py/
# .gitignore) pra já vir "quente" pra qualquer usuário na mesma resolução,
# sem precisar escanear a tela inteira na primeira vez.
COORDS_DIR = "coords"
os.makedirs(COORDS_DIR, exist_ok=True)
CACHE_FILE = os.path.join(COORDS_DIR, f"{RESOLUTION}_lobby.txt")

# Margem escala com a largura da tela: em resoluções ultrawide a lista de
# lobbies desloca mais os itens, e a janela de 60px (base 1920x1080) errava
# o alvo com mais frequência, caindo no fallback de scan em tela cheia
# (bem mais caro em telas maiores) — daí a demora reportada em 3440x1440.
try:
    _RES_WIDTH = int(RESOLUTION.lower().split("x")[0])
except Exception:
    _RES_WIDTH = 1920
CACHE_MARGIN = max(60, round(60 * _RES_WIDTH / 1920))  # px ao redor da coord salva para a região de busca rápida


def current_password() -> str:
    return PASSWORD_FIXED


def _delete_lock() -> None:
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass


# ==================================================
# PYAUTOGUI CONFIG
# ==================================================
pyautogui.PAUSE = 0.02
pyautogui.FAILSAFE = True


# ==================================================
# EMERGENCY STOP (ESC)
# ==================================================
def _matar_irmaos() -> None:
    """
    Esc em qualquer um dos três (lobby/in_game/painel) derruba os três.
    Pula o próprio .exe na lista: taskkill mata a própria imagem na hora
    (processo some no meio do for), o que abortaria antes de matar os
    outros - o próprio processo já se encerra sozinho com os._exit depois.
    start.py/start.exe fica de fora: é o launcher, esc não deve derrubá-lo.
    """
    if sys.platform != "win32":
        return
    exe_proprio = os.path.basename(sys.executable).lower() if getattr(sys, "frozen", False) else None
    for target in ("lobby.exe", "in_game.exe", "fim_game.exe", "painel.exe"):
        if target.lower() == exe_proprio:
            continue
        try:
            subprocess.run(["taskkill", "/F", "/IM", target],
                            startupinfo=HIDDEN_WINDOW, capture_output=True)
        except Exception:
            pass
    ps_script = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
        "Where-Object { $_.CommandLine -match 'lobby\\.py|in_game\\.py|fim_game\\.py|painel\\.py' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                        startupinfo=HIDDEN_WINDOW, capture_output=True)
    except Exception:
        pass

def _watch_esc() -> None:
    """
    GetAsyncKeyState em vez de 'keyboard': hotkey por nome depende do
    layout de teclado ativo e falha em layouts não-US (ex: russo);
    VK_ESCAPE é fixo independente de layout.
    """
    VK_ESCAPE = 0x1B
    while not (user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000):
        time.sleep(0.05)
    save_status(current_pw="", password_deadline=0.0)
    _delete_lock()
    print("\a")
    _matar_irmaos()
    os._exit(1)


# ==================================================
# WINDOW HELPERS
# ==================================================
def focus_dota() -> bool:
    if sys.platform != "win32":
        return False
    try:
        hwnd = user32.FindWindowW(None, "Dota 2")
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            time.sleep(FOCUS_WAIT)
            return True
    except Exception:
        pass
    return False


# ==================================================
# COORDINATE CACHE
# ==================================================
_coord_cache: dict[str, tuple[int, int]] = {}
_cache_lock = threading.Lock()


def _cache_load() -> None:
    _coord_cache.clear()
    if not os.path.exists(CACHE_FILE):
        return
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                name, coord = line.split("=", 1)
                x_str, y_str = coord.split(",", 1)
                _coord_cache[name] = (int(x_str), int(y_str))
    except Exception:
        pass


def _cache_write() -> None:
    # _clicker/_observer (threads paralelas em _refresh_until_game_appears) chamam
    # locate() ao mesmo tempo; sem lock, duas escritas concorrentes no mesmo
    # arquivo corrompem o cache (arquivo fica truncado/inválido).
    with _cache_lock:
        tmp_file = CACHE_FILE + ".tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                for name, (cx, cy) in _coord_cache.items():
                    f.write(f"{name}={cx},{cy}\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, CACHE_FILE)
        except Exception:
            pass


def _cache_save_entry(name: str, x: int, y: int) -> None:
    _coord_cache[name] = (x, y)
    _cache_write()


def _cache_invalidate(name: str) -> None:
    if name in _coord_cache:
        del _coord_cache[name]
        _cache_write()


# ==================================================
# IMAGE HELPERS
# ==================================================
def _img_path(name: str) -> str:
    return os.path.join(IMG_DIR, name)


Region = tuple[int, int, int, int]


def _locate_raw(
    name: str,
    confidence: float,
    region: Optional[Region] = None,
) -> Optional[tuple[int, int]]:
    try:
        return pyautogui.locateCenterOnScreen(
            _img_path(name),
            confidence=confidence,
            region=region,
        )
    except Exception:
        return None


def locate(name: str, confidence: float = 0.7) -> Optional[tuple[int, int]]:
    cached = _coord_cache.get(name)

    if cached is not None:
        cx, cy = cached
        region: Region = (
            max(0, cx - CACHE_MARGIN),
            max(0, cy - CACHE_MARGIN),
            CACHE_MARGIN * 2,
            CACHE_MARGIN * 2,
        )
        pos = _locate_raw(name, confidence, region=region)
        if pos:
            _update_debug(name, True)
            return pos
        _cache_invalidate(name)

    pos = _locate_raw(name, confidence)
    _update_debug(name, pos is not None)
    if pos:
        _cache_save_entry(name, pos[0], pos[1])
    return pos


def wait_for(
    name: str,
    confidence: float = 0.7,
    timeout: float = 60,
) -> Optional[tuple[int, int]]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        pos = locate(name, confidence)
        if pos:
            return pos
        time.sleep(0.3)
    return None


def safe_click(pos: Optional[tuple[int, int]], pause: float = CLICK_PAUSE) -> bool:
    if pos:
        pyautogui.moveTo(pos[0], pos[1])
        time.sleep(pause)
        pyautogui.click()
        return True
    return False


# ==================================================
# GAME FLOW
# ==================================================
def open_dota() -> None:
    if focus_dota():
        return
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "steam://run/570"],
            startupinfo=HIDDEN_WINDOW,
        )
        time.sleep(5.0)
    except Exception:
        os._exit(1)


def step_up_name() -> None:
    buscar = wait_for("buscar.png", confidence=0.60, timeout=10)
    if not buscar:
        return

    safe_click(buscar, pause=0.3)
    time.sleep(0.2)

    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.05)
    pyautogui.press("delete")
    time.sleep(0.1)

    pyautogui.write(UP_PREFIX, interval=0.05)
    time.sleep(0.3)


def step_menu() -> None:
    if not os.path.exists(IMG_DIR):
        os._exit(1)

    while True:
        focus_dota()

        if locate("lista.png"):
            break

        safe_click(locate("image.png"))
        time.sleep(MENU_STEP_WAIT)

    safe_click(locate("lista.png"))
    time.sleep(MENU_STEP_WAIT)

    sair = wait_for("sair.png", timeout=SAIR_TIMEOUT)
    if sair:
        safe_click(sair)
        time.sleep(MENU_STEP_WAIT)

    safe_click(wait_for("lobby.png"), pause=0.4)


def step_password() -> None:
    ok_pos = wait_for("ok.png")
    if not ok_pos:
        return

    time.sleep(0.3)
    focus_dota()
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("backspace")
    time.sleep(0.1)
    pyautogui.write(current_password(), interval=0.05)
    time.sleep(0.2)
    safe_click(ok_pos)


def _launch_in_game() -> None:
    if os.path.exists("in_game.exe"):
        subprocess.Popen(["in_game.exe"], startupinfo=HIDDEN_WINDOW)
    elif os.path.exists("in_game.py"):
        subprocess.Popen([sys.executable, "in_game.py"], startupinfo=HIDDEN_WINDOW)


def _restart_dota() -> None:
    try:
        subprocess.Popen(
            ["taskkill", "/F", "/IM", "dota2.exe"],
            startupinfo=HIDDEN_WINDOW,
        )
    except Exception:
        pass
    time.sleep(4.0)
    open_dota()
    time.sleep(6.0)


def _restart_with_current_password() -> None:
    """Mata/abre o Dota e refaz o fluxo completo usando a senha fixa."""
    _restart_dota()
    step_menu()
    step_password()
    step_up_name()


# ==================================================
# PÓS-CLIQUE EM LOBBY
# ==================================================
_ROOM_RESULT_SALA = "sala"
_ROOM_RESULT_ACEITAR = "aceitar"
_ROOM_RESULT_ERRO = "erro"


def _wait_after_room_click(timeout: float = 600) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if locate("erro.png"):
            return _ROOM_RESULT_ERRO
        if locate("aceitar.png"):
            return _ROOM_RESULT_ACEITAR
        if locate("sala.png"):
            return _ROOM_RESULT_SALA
        time.sleep(POLL_FAST)
    return _ROOM_RESULT_ERRO


def _accept_loop() -> bool:
    while True:
        err = locate("erro.png")
        if err:
            safe_click(err)
            time.sleep(0.1)
            return False

        if locate("fim.png"):
            _launch_in_game()
            return True

        time.sleep(POLL_FAST)


# ==================================================
# LOOP DE ATT INTELIGENTE
# ==================================================
def _refresh_until_game_appears() -> bool:
    """
    Clica em ATT continuamente em paralelo enquanto monitora se game.png aparece.
    Também monitora se full.png aparece; caso apareça, clica para fechar e continua.
    """
    att = locate("att.png")
    if not att:
        return False

    save_status(current_pw=current_password(), password_deadline=0.0)

    found_event = threading.Event()
    stop_event = threading.Event()

    def _clicker() -> None:
        current_att = att
        while not stop_event.is_set() and not found_event.is_set():
            safe_click(current_att, pause=POLL_ATT)
            wait_time = ATT_CYCLE_WAIT if "game.png" in _coord_cache else ATT_CYCLE_WAIT_NO_CACHE
            if found_event.wait(timeout=wait_time):
                return
            current_att = locate("att.png") or current_att

    def _observer() -> None:
        while not stop_event.is_set():
            # 1. Verifica se o jogo foi encontrado
            if locate("game.png", confidence=0.7):
                found_event.set()
                return

            # 2. Nova verificação: Se aparecer 'full.png', clica nela para fechar o aviso
            full_pop = locate("full.png", confidence=0.70)
            if full_pop:
                safe_click(full_pop, pause=0.1)
                time.sleep(0.2)  # Pausa rápida para o Dota processar o fechamento do popup

            time.sleep(POLL_FAST)

    clicker_thread = threading.Thread(target=_clicker, daemon=True)
    observer_thread = threading.Thread(target=_observer, daemon=True)
    clicker_thread.start()
    observer_thread.start()

    found = found_event.wait()  # Aguarda sem timeout
    stop_event.set()
    clicker_thread.join(timeout=2)
    observer_thread.join(timeout=2)

    return found

# ==================================================
# STEP LOBBY
# ==================================================
def step_lobby() -> None:
    lobby_ready = wait_for("200.png", timeout=30)
    if not lobby_ready:
        safe_click(locate("att.png"))
        time.sleep(1.0)

    save_status(rehost_max=REHOST_MAX, current_pw=current_password())

    inside_room = False

    while True:
        # ── ESTADO: dentro de uma sala ──────────────────────────────────────
        if inside_room:
            err = locate("erro.png")
            if err:
                safe_click(err, pause=0.1)
                time.sleep(0.2)
                _restart_with_current_password()
                inside_room = False
                continue

            aceitar = locate("aceitar.png")
            if aceitar:
                safe_click(aceitar)
                completed = _accept_loop()
                if completed:
                    return
                _restart_with_current_password()
                inside_room = False
                continue

            if not locate("sala.png"):
                inside_room = False

            time.sleep(POLL_FAST)
            continue

        # ── ESTADO: buscando lobby na lista ─────────────────────────────────
        err = locate("erro.png")
        if err:
            safe_click(err, pause=0.1)
            time.sleep(0.2)
            safe_click(locate("att.png"), pause=0.2)
            continue

        if locate("sala.png"):
            inside_room = True
            continue

        refreshed = _refresh_until_game_appears()
        if not refreshed:
            safe_click(locate("image.png"))
            time.sleep(MENU_STEP_WAIT)
            safe_click(locate("lista.png"))
            time.sleep(MENU_STEP_WAIT)
            wait_for("200.png", timeout=30)
            continue

        # Game encontrado → duplo-clique
        game = locate("game.png", confidence=0.7)
        if not game:
            continue

        pyautogui.moveTo(game[0], game[1])
        time.sleep(CLICK_PAUSE)
        pyautogui.doubleClick()

        result = _wait_after_room_click()

        if result == _ROOM_RESULT_ERRO:
            safe_click(locate("erro.png"), pause=0.1)
            _restart_with_current_password()

        elif result == _ROOM_RESULT_SALA:
            inside_room = True

        elif result == _ROOM_RESULT_ACEITAR:
            aceitar = locate("aceitar.png")
            if aceitar:
                safe_click(aceitar)
                completed = _accept_loop()
                if completed:
                    return
                _restart_with_current_password()


# ==================================================
# ENTRY POINT
# ==================================================
def main() -> None:
    threading.Thread(target=_watch_esc, daemon=True).start()
    _cache_load()

    open_dota()
    step_menu()
    step_password()
    time.sleep(0.5)
    step_up_name()
    step_lobby()

    _delete_lock()


if __name__ == "__main__":
    main()