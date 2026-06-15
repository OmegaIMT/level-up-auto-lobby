import os
import sys
import time
import threading
import subprocess
import pyautogui
import keyboard
from typing import Optional

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
# CONFIG
# ==================================================
LANGUAGE = os.environ.get("LANGUAGE_GLOBAL", "pt-br")

IMG_DIR = os.path.join("language", LANGUAGE, "in_game")
CACHE_FILE = "coords_cache_ingame.txt"  # cache separado do lobby
CACHE_MARGIN = 60  # px ao redor da coord salva

REHOST_MAX = int(os.environ.get("RE_HOST_GLOBAL", "2"))
CICLOS_FEITOS = int(os.environ.get("CICLOS_GLOBAL", "0"))
PARTIDAS_CONCLUIDAS = int(os.environ.get("PARTIDAS_CONCLUIDAS_GLOBAL", "0"))

TIMEOUT_SEM_COUNT = 4800  # 1h20min

POLL_IN_GAME = 2.0

pyautogui.PAUSE = 0.1
pyautogui.FAILSAFE = True


# ==================================================
# PERSISTENCE
# ==================================================
def save_status(partidas: int, rehost_max: int, ciclos: int) -> None:
    try:
        with open("panel_status.txt", "w") as f:
            f.write(f"{partidas}\n{rehost_max}\n{ciclos}")
    except Exception:
        pass


# ==================================================
# EMERGENCY STOP
# ==================================================
def _watch_esc() -> None:
    keyboard.wait("esc")
    print("\a")
    os._exit(1)


# ==================================================
# COORDINATE CACHE  (mesmo esquema do lobby)
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
Region = tuple[int, int, int, int]


def _locate_raw(
    name: str,
    confidence: float,
    region: Optional[Region] = None,
) -> Optional[tuple[int, int]]:
    try:
        return pyautogui.locateCenterOnScreen(
            os.path.join(IMG_DIR, name),
            confidence=confidence,
            region=region,
        )
    except Exception:
        return None


def locate(name: str, confidence: float = 0.85) -> Optional[tuple[int, int]]:
    """
    Busca com coordinate cache — full-screen só na primeira vez,
    depois vai direto na região salva.
    bonus.png é exceção: sempre full-screen (ver check_bonus).
    """
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


def safe_click(x: int, y: int, delay_after: float = 1.0) -> None:
    pyautogui.moveTo(x, y)
    time.sleep(0.2)
    pyautogui.click()
    time.sleep(delay_after)


def click_pos(pos, delay_after: float = 1.0) -> None:
    safe_click(pos[0], pos[1], delay_after)


def wait_for(
    name: str,
    confidence: float = 0.85,
    timeout: float = 15.0,
) -> Optional[tuple[int, int]]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        pos = locate(name, confidence)
        if pos:
            return pos
        time.sleep(0.3)
    return None


# ==================================================
# DISCONNECT & RELAUNCH LOBBY
# ==================================================
def disconnect_and_relaunch() -> None:
    """
    Fecha o Dota diretamente e relança o lobby.
    """

    try:
        if sys.platform == "win32":

            # Fecha o Dota 2
            os.system("taskkill /f /im dota2.exe >nul 2>&1")

            # Alguns builds usam dota2.exe filho do steam
            time.sleep(3)

    except Exception:
        pass

    pw_atual = os.environ.get("PW_GLOBAL", "")

    if os.path.exists("lobby.exe"):
        subprocess.Popen(
            ["lobby.exe", pw_atual],
            startupinfo=HIDDEN_WINDOW
        )
    else:
        subprocess.Popen(
            [sys.executable, "lobby.py", pw_atual],
            startupinfo=HIDDEN_WINDOW
        )

    os._exit(0)


# ==================================================
# MAIN MONITOR
# ==================================================
def monitor_match() -> None:
    bonus_deadline = time.time() + 60
    bonus_clicado = False
    global PARTIDAS_CONCLUIDAS, CICLOS_FEITOS

    count_ever_seen = False
    count_visible = False
    last_seen_time = time.time()

    while True:
        if not bonus_clicado and time.time() < bonus_deadline:
            bonus = _locate_raw("bonus.png", confidence=0.85)

            if bonus:
                click_pos(bonus, 1.0)

                cx = pyautogui.size().width // 2
                cy = pyautogui.size().height // 2

                pyautogui.moveTo(cx, cy)

                bonus_clicado = True
            pos_count = locate("count.png")

        if pos_count:
            if not count_ever_seen:
                count_ever_seen = True
                print("\a")

                PARTIDAS_CONCLUIDAS += 1
                save_status(PARTIDAS_CONCLUIDAS, REHOST_MAX, CICLOS_FEITOS)

                if PARTIDAS_CONCLUIDAS >= REHOST_MAX:
                    CICLOS_FEITOS += 1
                    os.environ["CICLOS_GLOBAL"] = str(CICLOS_FEITOS)
                    os.environ["PARTIDAS_CONCLUIDAS_GLOBAL"] = "0"
                    save_status(0, REHOST_MAX, CICLOS_FEITOS)
                    disconnect_and_relaunch()
                    return

                os.environ["PARTIDAS_CONCLUIDAS_GLOBAL"] = str(PARTIDAS_CONCLUIDAS)

            count_visible = True
            last_seen_time = time.time()

        else:
            tempo_sem_count = time.time() - last_seen_time

            if count_visible:
                count_visible = False
                time.sleep(2.0)
                if os.path.exists("in_game.exe"):
                    subprocess.Popen(["in_game.exe"], startupinfo=HIDDEN_WINDOW)
                else:
                    subprocess.Popen(
                        [sys.executable, "in_game.py"], startupinfo=HIDDEN_WINDOW
                    )
                os._exit(0)

            elif not count_ever_seen and tempo_sem_count > TIMEOUT_SEM_COUNT:
                os.environ["PARTIDAS_CONCLUIDAS_GLOBAL"] = "0"
                os.environ["CICLOS_GLOBAL"] = str(CICLOS_FEITOS)
                save_status(0, REHOST_MAX, CICLOS_FEITOS)
                disconnect_and_relaunch()
                return

        time.sleep(POLL_IN_GAME)


# ==================================================
# ENTRY POINT
# ==================================================
if __name__ == "__main__":
    threading.Thread(target=_watch_esc, daemon=True).start()
    _cache_load()

    save_status(PARTIDAS_CONCLUIDAS, REHOST_MAX, CICLOS_FEITOS)
    monitor_match()
