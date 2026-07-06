import json
import os
import subprocess
import sys
import threading
import time
from typing import Optional

import keyboard
import pyautogui

# ==================================================
# HIDE CONSOLE WINDOW (WINDOWS)
# ==================================================
if sys.platform == "win32":
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32")
    user32 = ctypes.WinDLL("user32")
    hWnd = kernel32.GetConsoleWindow()
    if hWnd:
        user32.ShowWindow(hWnd, 0)

HIDDEN_WINDOW = subprocess.STARTUPINFO()
HIDDEN_WINDOW.dwFlags |= subprocess.STARTF_USESHOWWINDOW
HIDDEN_WINDOW.wShowWindow = 0

# ==================================================
# TIMING CONSTANTS
# ==================================================
POLL_FAST = 0.03  # polling reativo (aguardando aceitar/erro)
POLL_NORMAL = 0.03  # polling padrão do loop de lobby
POLL_ATT = 0.02  # intervalo entre cliques no botão de atualizar
CLICK_PAUSE = 0.03  # pausa antes de cada clique
FOCUS_WAIT = 0.8  # tempo para o Windows processar foco
ATT_CYCLE_WAIT = 0.6  # espera após cada clique em ATT antes de checar
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
}


def save_status(
    partidas: int | None = None,
    rehost_max: int | None = None,
    ciclos: int | None = None,
    current_pw: str | None = None,
    password_deadline: float | None = None,
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

        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Erro ao salvar {STATUS_FILE}: {e}")


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

CACHE_FILE = "coords_cache.txt"
CACHE_MARGIN = 60  # px ao redor da coord salva para a região de busca rápida


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
def _watch_esc() -> None:
    keyboard.wait("esc")
    save_status(current_pw="", password_deadline=0.0)
    _delete_lock()
    print("\a")
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


def _cache_load() -> None:
    _coord_cache.clear()
    if not os.path.exists(CACHE_FILE):
        return
    try:
        with open(CACHE_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) == 3:
                    name, x, y = parts
                    _coord_cache[name] = (int(x), int(y))
    except Exception:
        pass


def _cache_save_entry(name: str, x: int, y: int) -> None:
    _coord_cache[name] = (x, y)
    try:
        with open(CACHE_FILE, "w") as f:
            for k, (cx, cy) in _coord_cache.items():
                f.write(f"{k}:{cx}:{cy}\n")
    except Exception:
        pass


def _cache_invalidate(name: str) -> None:
    if name in _coord_cache:
        del _coord_cache[name]
        try:
            with open(CACHE_FILE, "w") as f:
                for k, (cx, cy) in _coord_cache.items():
                    f.write(f"{k}:{cx}:{cy}\n")
        except Exception:
            pass


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


def locate(name: str, confidence: float = 0.80) -> Optional[tuple[int, int]]:
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
            return pos
        _cache_invalidate(name)

    pos = _locate_raw(name, confidence)
    if pos:
        _cache_save_entry(name, pos[0], pos[1])
    return pos


def wait_for(
    name: str,
    confidence: float = 0.80,
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


def _wait_after_room_click(timeout: float = 10) -> str:
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
            if found_event.wait(timeout=ATT_CYCLE_WAIT):
                return
            current_att = locate("att.png") or current_att

    def _observer() -> None:
        while not stop_event.is_set():
            # 1. Verifica se o jogo foi encontrado
            if locate("game.png", confidence=0.90):
                found_event.set()
                return

            # 2. Nova verificação: Se aparecer 'full.png', clica nela para fechar o aviso
            full_pop = locate("full.png", confidence=0.80)
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
            safe_click(locate("att.png"), pause=0.1)
            continue

        if locate("sala.png"):
            inside_room = True
            continue

        _refresh_until_game_appears()

        # Game encontrado → duplo-clique
        game = locate("game.png", confidence=0.75)
        if not game:
            continue

        pyautogui.moveTo(game[0], game[1])
        time.sleep(CLICK_PAUSE)
        pyautogui.doubleClick()

        result = _wait_after_room_click(timeout=10)

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
    step_up_name()
    step_lobby()

    _delete_lock()


if __name__ == "__main__":
    main()