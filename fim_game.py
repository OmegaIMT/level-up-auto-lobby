import os
import sys
import time
import json
import threading
import subprocess
import pyautogui
from typing import Optional

if sys.platform == "win32":
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32")
    user32   = ctypes.WinDLL("user32")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        user32.SetProcessDPIAware()
    hWnd = kernel32.GetConsoleWindow()
    if hWnd:
        user32.ShowWindow(hWnd, 0)

HIDDEN_WINDOW = subprocess.STARTUPINFO()
HIDDEN_WINDOW.dwFlags     |= subprocess.STARTF_USESHOWWINDOW
HIDDEN_WINDOW.wShowWindow  = 0

CONFIG_FILE = "config.json"

def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

CONFIG = load_config()

def save_config_update(**kwargs) -> None:
    cfg = load_config()
    cfg.update(kwargs)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

LANGUAGE   = CONFIG.get("language", "pt-br")
RESOLUTION = CONFIG.get("resolution", "1920x1080")


def _detect_zoom_pct() -> int:
    """Escala de exibição do Windows (100/125/150...), ver lobby.py."""
    if sys.platform != "win32":
        return 100
    try:
        return int(ctypes.windll.shcore.GetScaleFactorForDevice(0))
    except Exception:
        try:
            return round(user32.GetDpiForSystem() / 96 * 100)
        except Exception:
            return 100


ZOOM_PCT = _detect_zoom_pct()
RESOLUTION_KEY = f"{RESOLUTION}-{ZOOM_PCT}"

# IMG_DIR: bonus.png ("I am the champion"), dependente de idioma.
IMG_DIR = os.path.join("language", LANGUAGE, RESOLUTION, "in_game")

# GLOBAL_DIR: fonte.png (início da próxima partida), independente de idioma.
GLOBAL_DIR = os.path.join("language", "global", RESOLUTION)

REHOST_MAX          = int(CONFIG.get("rehost_max", 5))
CICLOS_FEITOS       = int(CONFIG.get("ciclos", 0))
PARTIDAS_CONCLUIDAS = int(CONFIG.get("partidas_concluidas", 0))

# coords/: mesmo esquema do in_game.py — cache de coordenadas próprio,
# separado do de in_game.py (processo diferente).
COORDS_DIR = "coords"
os.makedirs(COORDS_DIR, exist_ok=True)
CACHE_FILE = os.path.join(COORDS_DIR, f"{RESOLUTION_KEY}_fim_game.txt")
try:
    _RES_WIDTH = int(RESOLUTION.lower().split("x")[0])
except Exception:
    _RES_WIDTH = 1920
CACHE_MARGIN = max(60, round(60 * _RES_WIDTH / 1920))  # escala com a resolução (ver lobby.py)

# Tempo (s) esperando fonte.png aparecer após count sumir (fim de partida
# concluída, ainda não bateu rehost_max). Se estourar, mesmo fluxo dos
# outros timeouts: fecha dota, chama lobby de novo.
TIMEOUT_SEM_FONTE = 1800

pyautogui.PAUSE    = 0.1
pyautogui.FAILSAFE = True

_mouse_lock = threading.RLock()

STATUS_FILE = "status.json"

def save_status(partidas: int, rehost_max: int, ciclos: int) -> None:
    payload = {"partidas": partidas, "rehost_max": rehost_max, "ciclos": ciclos}
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# Debug ao vivo (painel.py): qual imagem locate() buscou por último e se achou.
_debug_lock = threading.Lock()
_last_debug: tuple[str, bool] | None = None
_last_debug_time = 0.0
DEBUG_MIN_INTERVAL = 0.15

def _update_debug(name: str, found: bool) -> None:
    global _last_debug, _last_debug_time
    now = time.time()
    with _debug_lock:
        if _last_debug == (name, found) and (now - _last_debug_time) < DEBUG_MIN_INTERVAL:
            return
        _last_debug = (name, found)
        _last_debug_time = now
    try:
        data = {}
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
        data["current_image"] = name
        data["image_found"] = found
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _matar_irmaos() -> None:
    """
    Esc em qualquer um dos quatro (lobby/in_game/fim_game/painel) derruba
    todos. Pula o próprio .exe na lista: taskkill mata a própria imagem na
    hora (processo some no meio do for), o que abortaria antes de matar os
    outros - o próprio processo já se encerra sozinho com os._exit depois.
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
    _matar_irmaos()
    os._exit(1)

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
    with _cache_lock:
        _coord_cache[name] = (x, y)
        _cache_write()

def _cache_invalidate(name: str) -> None:
    with _cache_lock:
        if name in _coord_cache:
            del _coord_cache[name]
            _cache_write()

Region = tuple[int, int, int, int]

def _global_img(*parts: str) -> str:
    """Caminho dentro de GLOBAL_DIR (independente de idioma, só por resolução)."""
    return os.path.join(GLOBAL_DIR, *parts)

def _locate_raw(path: str, confidence: float, region: Optional[Region] = None) -> Optional[tuple[int, int]]:
    try:
        return pyautogui.locateCenterOnScreen(path, confidence=confidence, region=region)
    except Exception:
        return None

def locate(cache_key: str, *path_parts: str, confidence: float = 0.75, base_dir: str = IMG_DIR) -> Optional[tuple[int, int]]:
    full_path = os.path.join(base_dir, *path_parts)
    if not os.path.exists(full_path):
        return None

    cached = _coord_cache.get(cache_key)
    if cached is not None:
        cx, cy = cached
        region: Region = (max(0, cx - CACHE_MARGIN), max(0, cy - CACHE_MARGIN), CACHE_MARGIN * 2, CACHE_MARGIN * 2)
        pos = _locate_raw(full_path, confidence, region=region)
        if pos:
            _update_debug(cache_key, True)
            return pos
        _cache_invalidate(cache_key)

    pos = _locate_raw(full_path, confidence)
    _update_debug(cache_key, pos is not None)
    if pos:
        _cache_save_entry(cache_key, pos[0], pos[1])
    return pos

def descansar_mouse() -> None:
    """Canto da tela, não o centro: os popups de fim de ciclo (fonte,
    cristal/equipamento) aparecem centralizados, e o cursor parado em cima
    deles atrapalhava o locateOnScreen da próxima detecção."""
    try:
        with _mouse_lock:
            pyautogui.moveTo(20, 20)
    except Exception:
        pass

def _click_at(x: int, y: int, right: bool = False, delay: float = 0.1, rest: bool = True) -> None:
    try:
        with _mouse_lock:
            pyautogui.moveTo(x, y)
            time.sleep(0.05)
            if right:
                pyautogui.rightClick()
            else:
                pyautogui.click()
            time.sleep(delay)
            if rest:
                descansar_mouse()
    except Exception:
        pass

def click_pos(pos: tuple[int, int], delay_after: float = 0.3, rest: bool = True) -> None:
    _click_at(pos[0], pos[1], delay=delay_after, rest=rest)

def wait_for_match_start(poll: float = 2.0, timeout: Optional[float] = None) -> bool:
    started_at = time.time()
    while True:
        if locate("fonte", "fonte.png", confidence=0.75, base_dir=GLOBAL_DIR):
            descansar_mouse()
            return True
        if timeout is not None and (time.time() - started_at) > timeout:
            return False
        time.sleep(poll)

POLL_BONUS = 3.0

def _bonus_watcher(wait_once: bool = False) -> None:
    """
    Fica clicando bonus.png ("I am the champion") sempre que aparecer -
    mesmo mecanismo que era do in_game.py durante a partida, agora só aqui
    (in_game.py morre via os._exit assim que count.png aparece, então quem
    cuida do bonus dali pra frente é o fim_game.py).

    wait_once=False (não é a última partida do ciclo): roda em thread solta,
    infinito, só de olho enquanto espera a próxima partida começar.

    wait_once=True (é a última partida do ciclo): chamada direta (bloqueia),
    espera aparecer, clica uma vez e retorna - só então fecha o dota.
    """
    while True:
        try:
            pos = locate("bonus", "bonus.png", confidence=0.75)
            if pos:
                click_pos(pos, 0.5)
                if wait_once:
                    return
        except Exception:
            pass
        time.sleep(POLL_BONUS)

def disconnect_and_relaunch() -> None:
    """Fecha o dota e volta pro lobby (fim do ciclo, ou algo travou)."""
    try:
        os.system("taskkill /f /im dota2.exe >nul 2>&1")
        time.sleep(3)
    except Exception:
        pass

    if os.path.exists("lobby.exe"):
        subprocess.Popen(["lobby.exe", CONFIG_FILE], startupinfo=HIDDEN_WINDOW)
    else:
        subprocess.Popen([sys.executable, "lobby.py", CONFIG_FILE], startupinfo=HIDDEN_WINDOW)
    os._exit(0)

def _launch_in_game() -> None:
    """Puxa o in_game de novo pra próxima partida do mesmo ciclo."""
    if os.path.exists("in_game.exe"):
        subprocess.Popen(["in_game.exe"], startupinfo=HIDDEN_WINDOW)
    elif os.path.exists("in_game.py"):
        subprocess.Popen([sys.executable, "in_game.py"], startupinfo=HIDDEN_WINDOW)
    os._exit(0)

def processar_fim_partida() -> None:
    global PARTIDAS_CONCLUIDAS, CICLOS_FEITOS

    PARTIDAS_CONCLUIDAS += 1
    save_status(PARTIDAS_CONCLUIDAS, REHOST_MAX, CICLOS_FEITOS)
    save_config_update(partidas_concluidas=PARTIDAS_CONCLUIDAS)

    if PARTIDAS_CONCLUIDAS >= REHOST_MAX:
        # Última partida do ciclo: espera o bonus aparecer e clica antes de
        # fechar (bloqueia aqui, só segue depois de clicar).
        _bonus_watcher(wait_once=True)

        CICLOS_FEITOS += 1
        save_status(0, REHOST_MAX, CICLOS_FEITOS)
        save_config_update(partidas_concluidas=0, ciclos=CICLOS_FEITOS)
        disconnect_and_relaunch()
        return

    # Ainda não é a última partida do ciclo: fica de olho em bonus.png
    # enquanto espera a próxima partida começar (ver _bonus_watcher).
    threading.Thread(target=_bonus_watcher, daemon=True).start()

    # Espera a próxima partida começar (fonte.png). Se fonte não aparecer
    # em TIMEOUT_SEM_FONTE, mesmo fluxo dos outros timeouts: fecha dota,
    # chama lobby de novo.
    if not wait_for_match_start(timeout=TIMEOUT_SEM_FONTE):
        CICLOS_FEITOS += 1
        save_status(0, REHOST_MAX, CICLOS_FEITOS)
        save_config_update(partidas_concluidas=0, ciclos=CICLOS_FEITOS)
        disconnect_and_relaunch()
        return

    _launch_in_game()

if __name__ == "__main__":
    threading.Thread(target=_watch_esc, daemon=True).start()
    _cache_load()

    processar_fim_partida()
