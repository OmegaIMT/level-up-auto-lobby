import os
import sys
import time
import json
import threading
import subprocess
import pyautogui
import keyboard
from typing import Optional, List

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
NO_XP      = bool(CONFIG.get("no_xp", True))
CRYSTAL    = bool(CONFIG.get("crystal", True))
EQUIPMENT  = bool(CONFIG.get("equipment", True))
SUPORTE    = bool(CONFIG.get("support", True))

# IMG_DIR: agora só guarda o que continua dependente de idioma (bonus, count).
IMG_DIR = os.path.join("language", LANGUAGE, RESOLUTION, "in_game")

# GLOBAL_DIR: imagens independentes de idioma, só dependem da resolução.
# Aqui vivem: fonte.png, a pasta "suporte" inteira (hammer/pill/tesouro/slot),
# a pasta "event" e a pasta "error".
GLOBAL_DIR = os.path.join("language", "global", RESOLUTION)

REHOST_MAX          = int(CONFIG.get("rehost_max", 5))
CICLOS_FEITOS       = int(CONFIG.get("ciclos", 0))
PARTIDAS_CONCLUIDAS = int(CONFIG.get("partidas_concluidas", 0))

CACHE_FILE        = f"cache_in_game_{RESOLUTION}.txt"
CACHE_MARGIN      = 60
POLL_IN_GAME      = 2.0
POLL_BONUS        = 3.0
POLL_TESOURO      = 10.0
POLL_STATUS       = 30.0
TIMEOUT_SEM_COUNT = 4800

# Tempo (s) sem ver count.png a partir do qual passamos a checar as imagens
# de erro na pasta global "error".
ERROR_CHECK_SECONDS = 600
ERROR_DIR_NAME       = "error"

# Espera antes de começar a procurar o evento após o início da partida;
# depois disso, busca contínua (ver buscar_evento).
EVENTO_WAIT_FIRST = 360  # 6 min
EVENTO_POLL = 5.0

pyautogui.PAUSE    = 0.1
pyautogui.FAILSAFE = True

# ==================================================
# MOUSE LOCK
# Todas as ações de mouse passam por aqui, serializadas, pra evitar que as
# threads (bonus/tesouro/status) disputem o cursor ao mesmo tempo — era
# isso que impedia o mouse de ficar parado no "descanso".
# ==================================================
_mouse_lock = threading.RLock()
_stop_extras = threading.Event()

# Serializa status/tesouro: uma vez por vez, nunca simultâneo (fila de espera).
_extras_lock = threading.Lock()

STATUS_FILE = "status.json"

def save_status(partidas: int, rehost_max: int, ciclos: int) -> None:
    payload = {"partidas": partidas, "rehost_max": rehost_max, "ciclos": ciclos}
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# Debug ao vivo (painel.py): qual imagem locate() buscou por último e se achou.
# Throttle pra não gerar I/O em disco a cada poll rápido do loop.
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

def _watch_esc() -> None:
    keyboard.wait("esc")
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

def _img(*parts: str) -> str:
    """Caminho dentro de IMG_DIR (dependente de idioma) — hoje só bonus/count."""
    return os.path.join(IMG_DIR, *parts)

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
    try:
        if SLOT_20_BASE:
            x, y = scale_coord(SLOT_20_BASE)
        else:
            w, h = pyautogui.size()
            x, y = w // 2, h // 2
        with _mouse_lock:
            pyautogui.moveTo(x, y)
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

def click_centro_tela() -> None:
    w, h = pyautogui.size()
    _click_at(w // 2, h // 2, delay=0.2)

# ==================================================
# COORDENADAS FIXAS + ESCALA DE RESOLUÇÃO
# ==================================================
COORDS_FILE = "coords_base.json"

def load_coords_base() -> dict:
    if not os.path.exists(COORDS_FILE):
        return {}
    try:
        with open(COORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

COORDS_BASE = load_coords_base()

_captured_res = COORDS_BASE.get("captured_resolution", "1920x1080")
BASE_WIDTH, BASE_HEIGHT = (int(v) for v in _captured_res.split("x"))

def _c(key: str) -> Optional[tuple[int, int]]:
    return tuple(COORDS_BASE[key]) if key in COORDS_BASE else None

SLOT_20_BASE = _c("slot_20")

XP_BUTTON_BASE              = _c("no_xp")
PUBLIC_BACKPACK_TARGET_BASE = _c("public_backpack_target")
ORGANIZAR_BASE              = _c("organizar")
GOLD_BASE                   = _c("gold")
STATUS_BASE                 = _c("status")

STATUS_LIST_BASE = [_c(f"status_{i}") for i in range(1, 13)]
STATUS_11_BASE = STATUS_LIST_BASE[10]
STATUS_12_BASE = STATUS_LIST_BASE[11]

BACKPACK_SLOTS_BASE: list[tuple[int, int]] = [
    tuple(COORDS_BASE[k]) for k in sorted(COORDS_BASE.keys()) if k.startswith("slot_")
][:2]

RESOLUTION_OFFSET = {
    "3440x1440": (50, -25),  # (x, y) em px: + direita / + baixo
}

def scale_coord(coord_base: tuple[int, int]) -> tuple[int, int]:
    bx, by = coord_base
    try:
        tw, th = (int(v) for v in RESOLUTION.lower().split("x"))
    except Exception:
        tw, th = BASE_WIDTH, BASE_HEIGHT
    sx = tw / BASE_WIDTH
    sy = th / BASE_HEIGHT
    x, y = int(round(bx * sx)), int(round(by * sy))

    off = RESOLUTION_OFFSET.get(RESOLUTION.lower())
    if off:
        x += off[0]
        y += off[1]

    return x, y

def drag_item(src: tuple[int, int], dst: tuple[int, int], duration: float = 0.15) -> None:
    sx, sy = src
    dx, dy = dst
    try:
        with _mouse_lock:
            pyautogui.moveTo(sx, sy)
            time.sleep(0.05)
            pyautogui.mouseDown()
            time.sleep(0.05)
            pyautogui.moveTo(dx, dy, duration=duration)
            time.sleep(0.05)
            pyautogui.mouseUp()
            time.sleep(0.05)
            descansar_mouse()
    except Exception:
        try:
            pyautogui.mouseUp()
        except Exception:
            pass

SLOT_CHECK_HALF = 30

def is_slot_occupied(coord_base: tuple[int, int]) -> bool:
    x, y = scale_coord(coord_base)
    half = SLOT_CHECK_HALF
    region: Region = (max(0, x - half), max(0, y - half), half * 2, half * 2)
    return _locate_raw(_global_img("suporte", "slot.png"), confidence=0.75, region=region) is None

def click_organizar() -> None:
    if ORGANIZAR_BASE is None:
        return
    x, y = scale_coord(ORGANIZAR_BASE)
    _click_at(x, y, delay=0.4)

def verificar_e_mover_itens(quantidade: Optional[int] = None) -> None:
    if not BACKPACK_SLOTS_BASE or PUBLIC_BACKPACK_TARGET_BASE is None:
        return

    click_organizar()

    occupied = [s for s in BACKPACK_SLOTS_BASE if is_slot_occupied(s)]
    if not occupied:
        descansar_mouse()
        return

    itens = occupied if quantidade is None else occupied[:quantidade]
    dst = scale_coord(PUBLIC_BACKPACK_TARGET_BASE)

    for slot_base in itens:
        drag_item(scale_coord(slot_base), dst)

def verificar_e_mover_itens_slots(indices: list[int]) -> None:
    if not BACKPACK_SLOTS_BASE or PUBLIC_BACKPACK_TARGET_BASE is None:
        return

    click_organizar()

    slots = [BACKPACK_SLOTS_BASE[i] for i in indices if i < len(BACKPACK_SLOTS_BASE)]
    if not slots:
        return

    occupied = [s for s in slots if is_slot_occupied(s)]
    if not occupied:
        descansar_mouse()
        return

    dst = scale_coord(PUBLIC_BACKPACK_TARGET_BASE)
    for slot_base in occupied:
        drag_item(scale_coord(slot_base), dst)

def subir_status() -> None:
    if GOLD_BASE is None or STATUS_BASE is None:
        return

    gold_pos = scale_coord(GOLD_BASE)
    status_pos = scale_coord(STATUS_BASE)

    # Se a loja (shop.png) já tá aberta, o clique inicial no gold fecha ela
    # à toa — pula e só clica no gold no fim, igual antes.
    loja_aberta = locate("shop", "shop.png", confidence=0.75) is not None

    if not loja_aberta:
        _click_at(*gold_pos, delay=0.5)

    hammer_pos = locate("hammer", "suporte", "hammer.png", confidence=0.8, base_dir=GLOBAL_DIR)
    pill_pos = locate("pill", "suporte", "pill.png", confidence=0.8, base_dir=GLOBAL_DIR)

    if hammer_pos or pill_pos:
        if STATUS_11_BASE:
            pos = scale_coord(STATUS_11_BASE)
            for _ in range(3):
                _click_at(*pos, delay=0.5)
        if STATUS_12_BASE:
            pos = scale_coord(STATUS_12_BASE)
            for _ in range(2):
                _click_at(*pos, delay=0.5)
    else:
        shop_global_pos = locate("shop_global", "shop.png", confidence=0.75, base_dir=GLOBAL_DIR)
        if not shop_global_pos:
            for _ in range(8):
                _click_at(*status_pos, delay=0.5)
        else:
            for status_base in STATUS_LIST_BASE:
                if status_base:
                    x, y = scale_coord(status_base)
                    _click_at(x, y, right=True, delay=0.1)

    _click_at(*gold_pos, delay=0.5)

def monitorar_status() -> None:
    while not _stop_extras.is_set():
        with _extras_lock:
            try:
                loja_aberta = locate("shop", "shop.png", confidence=0.75) is not None

                if GOLD_BASE and not loja_aberta:
                    _click_at(*scale_coord(GOLD_BASE), delay=0.5)

                if _stop_extras.is_set():
                    break

                hammer_pos = locate("hammer", "suporte", "hammer.png", confidence=0.8, base_dir=GLOBAL_DIR)
                pill_pos = locate("pill", "suporte", "pill.png", confidence=0.8, base_dir=GLOBAL_DIR)

                if hammer_pos or pill_pos:
                    if STATUS_11_BASE:
                        pos = scale_coord(STATUS_11_BASE)
                        for _ in range(3):
                            if _stop_extras.is_set():
                                break
                            _click_at(*pos, delay=0.5)
                    if not _stop_extras.is_set() and STATUS_12_BASE:
                        pos = scale_coord(STATUS_12_BASE)
                        for _ in range(2):
                            if _stop_extras.is_set():
                                break
                            _click_at(*pos, delay=0.5)
                    if _stop_extras.is_set():
                        break
                    verificar_e_mover_itens_slots([0, 1, 2, 3])
                else:
                    shop_global_pos = locate("shop_global", "shop.png", confidence=0.75, base_dir=GLOBAL_DIR)
                    if not shop_global_pos and STATUS_BASE:
                        pos = scale_coord(STATUS_BASE)
                        for _ in range(8):
                            if _stop_extras.is_set():
                                break
                            _click_at(*pos, delay=0.5)
                    else:
                        for status_base in STATUS_LIST_BASE:
                            if _stop_extras.is_set():
                                break
                            if status_base:
                                x, y = scale_coord(status_base)
                                _click_at(x, y, right=True, delay=0.1)
                    if _stop_extras.is_set():
                        break
                    verificar_e_mover_itens_slots([0, 1, 2, 3])

                if _stop_extras.is_set():
                    break

                if GOLD_BASE:
                    _click_at(*scale_coord(GOLD_BASE), delay=0.5)

            except Exception:
                pass

        _stop_extras.wait(POLL_STATUS)

_tesouros_clicados: List[str] = []

def carregar_imagens_tesouro() -> List[str]:
    pasta = os.path.join(GLOBAL_DIR, "suporte", "tesouro")
    if not os.path.exists(pasta):
        return []
    imagens = []
    for arquivo in sorted(os.listdir(pasta)):
        if arquivo.endswith(".png"):
            nome = os.path.splitext(arquivo)[0]
            if nome.isdigit():
                imagens.append((int(nome), arquivo))
    imagens.sort(key=lambda x: x[0])
    return [img[1] for img in imagens]

def encontrar_tesouro_principal() -> Optional[tuple[int, int]]:
    for conf in (0.85, 0.8, 0.75, 0.6):
        pos = locate("tesouro", "suporte", "tesouro.png", confidence=conf, base_dir=GLOBAL_DIR)
        if pos:
            return pos
    return None

def monitorar_tesouro() -> None:
    global _tesouros_clicados
    _tesouros_clicados = []
    imagens_tesouro = carregar_imagens_tesouro()
    if not imagens_tesouro:
        return

    while not _stop_extras.is_set():
        with _extras_lock:
            try:
                pos_tesouro = encontrar_tesouro_principal()

                if pos_tesouro and not _stop_extras.is_set():
                    click_pos(pos_tesouro, 0.5)
                    encontrou = False

                    # Sempre reinicia em 0.9 primeiro; só cai pra 0.6 se não achar.
                    for confianca in (0.9, 0.6):
                        if encontrou or _stop_extras.is_set():
                            break
                        for img_nome in imagens_tesouro:
                            if _stop_extras.is_set():
                                break
                            if confianca == 0.9 and img_nome in _tesouros_clicados:
                                continue

                            img_path = os.path.join(GLOBAL_DIR, "suporte", "tesouro", img_nome)
                            pos = _locate_raw(img_path, confidence=confianca)
                            if not pos:
                                continue

                            encontrou = True
                            click_pos(pos, 0.5)
                            if confianca == 0.9:
                                # achou com confiança alta -> não busca essa de novo (mais rápido)
                                _tesouros_clicados.append(img_nome)
                            # achou em 0.6 -> não entra na lista, continua elegível sempre

                            if _stop_extras.is_set():
                                break
                            time.sleep(0.5)
                            verificar_e_mover_itens()
                            break

                    if not encontrou and not _stop_extras.is_set():
                        click_centro_tela()
            except Exception:
                pass

        _stop_extras.wait(POLL_TESOURO)

def esperar_e_clicar_bonus(vezes: int = 1) -> None:
    restantes = vezes
    poll_rapido = 0.3

    while restantes > 0:
        pos = locate("bonus", "bonus.png", confidence=0.75)
        if pos:
            click_pos(pos, 0.2)
            restantes -= 1

            # espera essa aparição sumir antes de procurar a próxima,
            # evita clicar duas vezes na mesma e evita perder uma que
            # aparece/some rápido em sequência
            espera_sumir = time.time()
            while locate("bonus", "bonus.png", confidence=0.75):
                if time.time() - espera_sumir > 5:
                    break
                time.sleep(poll_rapido)
        else:
            time.sleep(poll_rapido)

def disable_xp() -> None:
    if not NO_XP or XP_BUTTON_BASE is None:
        return
    x, y = scale_coord(XP_BUTTON_BASE)
    _click_at(x, y, right=True, delay=0.2)

def wait_for_match_start(poll: float = 2.0, timeout: Optional[float] = None) -> bool:
    started_at = time.time()
    while True:
        if locate("fonte", "fonte.png", confidence=0.75, base_dir=GLOBAL_DIR):
            descansar_mouse()
            return True
        if timeout is not None and (time.time() - started_at) > timeout:
            return False
        time.sleep(poll)

def disconnect_and_relaunch() -> None:
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

def _bonus_watcher() -> None:
    while True:
        try:
            pos = locate("bonus", "bonus.png", confidence=0.75)
            if pos:
                click_pos(pos, 0.5)
        except Exception:
            pass
        time.sleep(POLL_BONUS)

# ==================================================
# EVENTO (global, independe de idioma/SUPORTE)
# ==================================================
def buscar_evento() -> None:
    """
    6 min após o início da partida, começa a procurar
    language/global/RESOLUTION/event/event.png continuamente. Só para
    quando achar (clica e encerra) ou quando a partida encerra (count.png
    achado -> _stop_extras, ver monitor_match).
    """
    if _stop_extras.wait(timeout=EVENTO_WAIT_FIRST):
        return  # partida encerrou antes de começar a procurar

    while not _stop_extras.is_set():
        pos = _locate_raw(_global_img("event", "event.png"), confidence=0.75)
        if pos:
            click_pos(pos, 0.3, rest=False)
            return
        if _stop_extras.wait(timeout=EVENTO_POLL):
            return  # partida encerrou enquanto procurava

# ==================================================
# ERRO (global, independe de idioma)
# ==================================================
def carregar_imagens_erro() -> List[str]:
    pasta = _global_img(ERROR_DIR_NAME)
    if not os.path.exists(pasta):
        return []
    return sorted(f for f in os.listdir(pasta) if f.endswith(".png"))

def verificar_erro() -> Optional[str]:
    for nome in carregar_imagens_erro():
        caminho = _global_img(ERROR_DIR_NAME, nome)
        if _locate_raw(caminho, confidence=0.75):
            return nome
    return None

def monitor_match() -> None:
    global PARTIDAS_CONCLUIDAS, CICLOS_FEITOS

    count_ever_seen = False
    last_seen_time = time.time()
    erro_verificado = False

    while True:
        pos_count = locate("count", "count.png", confidence=0.70)

        if pos_count and not count_ever_seen:
            count_ever_seen = True
            _stop_extras.set()

            PARTIDAS_CONCLUIDAS += 1
            save_status(PARTIDAS_CONCLUIDAS, REHOST_MAX, CICLOS_FEITOS)
            save_config_update(partidas_concluidas=PARTIDAS_CONCLUIDAS)

            if PARTIDAS_CONCLUIDAS >= REHOST_MAX:
                vezes_bonus = int(CRYSTAL) + int(EQUIPMENT)
                if vezes_bonus > 0:
                    esperar_e_clicar_bonus(vezes_bonus)

                CICLOS_FEITOS += 1
                save_status(0, REHOST_MAX, CICLOS_FEITOS)
                save_config_update(partidas_concluidas=0, ciclos=CICLOS_FEITOS)
                disconnect_and_relaunch()
                return

            # Espera a próxima partida começar
            wait_for_match_start(timeout=None)

            iniciar_partida()

            count_ever_seen = False
            last_seen_time = time.time()
            erro_verificado = False

        elif not count_ever_seen:
            elapsed = time.time() - last_seen_time

            # Checagem de erro: só uma vez por ciclo de espera, depois de ERROR_CHECK_SECONDS.
            if not erro_verificado and elapsed > ERROR_CHECK_SECONDS:
                erro_verificado = True
                nome_erro = verificar_erro()
                if nome_erro:
                    # Mesmo comportamento de quando atinge o max de partidas:
                    # fecha o dota, chama o lobby e salva mais um ciclo.
                    CICLOS_FEITOS += 1
                    save_status(0, REHOST_MAX, CICLOS_FEITOS)
                    save_config_update(partidas_concluidas=0, ciclos=CICLOS_FEITOS)
                    disconnect_and_relaunch()
                    return

            if elapsed > TIMEOUT_SEM_COUNT:
                save_status(0, REHOST_MAX, CICLOS_FEITOS)
                save_config_update(partidas_concluidas=0, ciclos=CICLOS_FEITOS)
                disconnect_and_relaunch()
                return

        time.sleep(POLL_IN_GAME)

def iniciar_partida(criar_threads=True):
    _stop_extras.clear()

    disable_xp()

    if SUPORTE:
        subir_status()
        verificar_e_mover_itens()

    if criar_threads:
        threading.Thread(target=_bonus_watcher, daemon=True).start()
        threading.Thread(target=buscar_evento, daemon=True).start()
        if SUPORTE:
            threading.Thread(target=monitorar_tesouro, daemon=True).start()
            threading.Thread(target=monitorar_status, daemon=True).start()

if __name__ == "__main__":
    threading.Thread(target=_watch_esc, daemon=True).start()
    _cache_load()

    if not wait_for_match_start(timeout=None):
        sys.exit(1)

    iniciar_partida()

    save_status(PARTIDAS_CONCLUIDAS, REHOST_MAX, CICLOS_FEITOS)
    monitor_match()