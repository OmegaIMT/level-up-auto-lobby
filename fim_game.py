import os
import sys
import time
import json
import glob
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
CACHE_FILE = os.path.join(COORDS_DIR, f"{RESOLUTION}_fim_game.txt")
try:
    _RES_WIDTH = int(RESOLUTION.lower().split("x")[0])
except Exception:
    _RES_WIDTH = 1920
CACHE_MARGIN = max(60, round(60 * _RES_WIDTH / 1920))  # escala com a resolução (ver lobby.py)

# ==================================================
# VENDER (wings/equipamento) - coordenadas fixas capturadas via
# coord_capture.py, uma por resolução (Dota não segue a escala do Windows).
# ==================================================
RANKS_ORDER = ["b", "a", "s", "ss", "sss", "ex"]

VENDER_COORDS_FILE = os.path.join(COORDS_DIR, "coords_base_vender.json")

def load_vender_coords() -> dict:
    if not os.path.exists(VENDER_COORDS_FILE):
        return {}
    try:
        with open(VENDER_COORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

VENDER_COORDS_ALL = load_vender_coords()
VENDER_COORDS = VENDER_COORDS_ALL.get(RESOLUTION.lower()) or VENDER_COORDS_ALL.get(RESOLUTION) or {}
WINGS_COORDS = VENDER_COORDS.get("wings", {})
EQUIP_COORDS = VENDER_COORDS.get("equipamento", {})
HERO_COORDS = VENDER_COORDS.get("hero", {})

# slot_20 (mesmo ponto "neutro" usado pelo in_game.py pra descansar o mouse
# longe de um slot de item, evita hover/tooltip atrapalhar) - só reaproveita
# o arquivo de coords do in_game aqui, sem puxar o módulo inteiro.
IN_GAME_COORDS_FILE = os.path.join(COORDS_DIR, "coords_base_in_game.json")

def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

IN_GAME_COORDS_ALL = _load_json(IN_GAME_COORDS_FILE)
IN_GAME_COORDS = IN_GAME_COORDS_ALL.get(RESOLUTION.lower()) or IN_GAME_COORDS_ALL.get(RESOLUTION) or {}
SLOT_20 = IN_GAME_COORDS.get("slot_20")

# {"b": bool, "a": bool, ...} - vem do painel "Vender" do start.py.
SELL_WINGS = CONFIG.get("sell_wings", {})
SELL_EQUIPMENT = CONFIG.get("sell_equipment", {})

# Toggle "endless" (painel Vender) - entra o mapa Endless Trial depois de
# vender wings/equipamento.
ENDLESS = bool(CONFIG.get("endless", False))
ENDLESS_CLICK_DELAY = 0.5
# dog.png agora é só o texto do label (sem a montaria - sprite anima e não
# batia sempre). A montaria/npc clicável fica abaixo do texto, a uma
# distância que escala com o tamanho do template encontrado (resolução e
# zoom do mapa variam - offset fixo em pixel não acompanha). Clique cai em
# box.top + box.height * DOG_CLICK_Y_RATIO - chute inicial, calibrar vendo
# onde cai de verdade no jogo.
DOG_CLICK_Y_RATIO = 2.3

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
    alvos = [t for t in ("lobby.exe", "in_game.exe", "fim_game.exe", "painel.exe") if t != exe_proprio]

    if alvos:
        try:
            args = ["taskkill", "/F"]
            for t in alvos:
                args += ["/IM", t]
            subprocess.Popen(args, startupinfo=HIDDEN_WINDOW,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    ps_script = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
        "Where-Object { $_.CommandLine -match 'lobby\\.py|in_game\\.py|fim_game\\.py|painel\\.py' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                          startupinfo=HIDDEN_WINDOW,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

def _locate_box_raw(path: str, confidence: float, region: Optional[Region] = None):
    try:
        return pyautogui.locateOnScreen(path, confidence=confidence, region=region)
    except Exception:
        return None

def locate_box(cache_key: str, *path_parts: str, confidence: float = 0.75, base_dir: str = IMG_DIR):
    """Igual locate(), mas devolve a caixa (left, top, width, height) em vez
    do centro - usado quando o clique real não é no centro do template e
    precisa escalar com o tamanho encontrado (ex: dog.png, ver
    DOG_CLICK_Y_RATIO)."""
    full_path = os.path.join(base_dir, *path_parts)
    if not os.path.exists(full_path):
        return None

    cached = _coord_cache.get(cache_key)
    if cached is not None:
        cx, cy = cached
        region: Region = (max(0, cx - CACHE_MARGIN), max(0, cy - CACHE_MARGIN), CACHE_MARGIN * 2, CACHE_MARGIN * 2)
        box = _locate_box_raw(full_path, confidence, region=region)
        if box:
            _update_debug(cache_key, True)
            return box
        _cache_invalidate(cache_key)

    box = _locate_box_raw(full_path, confidence)
    _update_debug(cache_key, box is not None)
    if box:
        _cache_save_entry(cache_key, box.left + box.width // 2, box.top + box.height // 2)
    return box

def descansar_mouse() -> None:
    """Canto da tela, não o centro: os popups de fim de ciclo (fonte,
    cristal/equipamento) aparecem centralizados, e o cursor parado em cima
    deles atrapalhava o locateOnScreen da próxima detecção."""
    try:
        with _mouse_lock:
            pyautogui.moveTo(20, 20)
    except Exception:
        pass

def _click_at(x: int, y: int, right: bool = False, delay: float = 0.1, rest: bool = True, pre_delay: float = 0.05) -> None:
    """pre_delay: pausa entre mover o mouse e clicar - moveTo é instantâneo
    (sem duration), então em cliques mais sensíveis (ex: mapa do endless) o
    jogo às vezes ainda não processou a posição nova do cursor quando o
    clique já disparou. Padrão 0.05 mantém o comportamento de antes; suba
    esse valor pra cliques que estão saindo imprecisos."""
    try:
        with _mouse_lock:
            pyautogui.moveTo(x, y)
            time.sleep(pre_delay)
            if right:
                pyautogui.rightClick()
            else:
                pyautogui.click()
            time.sleep(delay)
            if rest:
                descansar_mouse()
    except Exception:
        pass

def click_pos(pos: tuple[int, int], delay_after: float = 0.3, rest: bool = True, pre_delay: float = 0.05) -> None:
    _click_at(pos[0], pos[1], delay=delay_after, rest=rest, pre_delay=pre_delay)

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

# Setado pelo _bonus_watcher sempre que clica bonus.png - os fluxos de venda
# (vender_wings/vender_equipamento) checam isso pra saber se o popup atrapalhou
# os cliques deles (fica por cima da tela) e precisam refazer o fluxo do zero.
_bonus_interrupt = threading.Event()

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
                _bonus_interrupt.set()
                if wait_once:
                    return
        except Exception:
            pass
        time.sleep(POLL_BONUS)

BONUS_INTERRUPT_MAX_RETRY = 5

def _rodar_com_retry_bonus(fluxo) -> None:
    """Se bonus.png aparecer (e for clicado pelo _bonus_watcher) enquanto
    `fluxo` roda, o popup atrapalhou os cliques de coordenada fixa - refaz o
    fluxo inteiro do zero, até BONUS_INTERRUPT_MAX_RETRY vezes. Não usado
    pro ativar_endless (ver processar_fim_partida)."""
    for _ in range(BONUS_INTERRUPT_MAX_RETRY):
        _bonus_interrupt.clear()
        fluxo()
        if not _bonus_interrupt.is_set():
            return

def _clicar_vender(coords: dict, chave: str, espera: float = 0.3, pre_delay: float = 0.05) -> None:
    pos = coords.get(chave)
    if not pos:
        return
    click_pos(tuple(pos), delay_after=espera, rest=False, pre_delay=pre_delay)

# Confirmação visual (forja.png/pena.png) de que a loja realmente abriu
# depois do clique no botão - imagens fixas (idioma-independente), mas
# comparadas contra a tela do jogo de verdade, então tem que ser da
# resolução certa (diferente dos ícones de rank do start.py, que só
# desenham na própria janela Tkinter e não precisam bater com a tela).
CONFIRM_BUTTON_DIR = os.path.join("language", "global", RESOLUTION, "buttons")
CONFIRM_SHOP_MAX_TENTATIVAS = 5
CONFIRM_SHOP_TIMEOUT = 4.0

def _abrir_loja_com_confirmacao(coords: dict, botao_key: str, cache_key: str, img_name: str) -> bool:
    """Clica botao_key (abre a loja) e espera a confirmação visual
    (forja.png/pena.png) aparecer; se não aparecer dentro do timeout, clica
    de novo - até CONFIRM_SHOP_MAX_TENTATIVAS vezes. Coordenada da
    confirmação fica cacheada automaticamente pelo locate() (mesmo cache de
    coords/{RES}_fim_game.txt), pra achar mais rápido da próxima vez."""
    for _ in range(CONFIRM_SHOP_MAX_TENTATIVAS):
        _clicar_vender(coords, botao_key, 3.0)
        started = time.time()
        while time.time() - started < CONFIRM_SHOP_TIMEOUT:
            if locate(cache_key, img_name, confidence=0.75, base_dir=CONFIRM_BUTTON_DIR):
                return True
            time.sleep(0.5)
    return False

def vender_wings() -> None:
    """
    Abre a loja de Wings, abre a lista de itens (buy) uma vez só, marca
    (clica) cada rank selecionado em sequência e só então confirma a compra
    inteira de uma vez (buy_2/confirm/ok) - não reabre buy nem confirma por
    rank individualmente.
    """
    ranks = [r for r in RANKS_ORDER if SELL_WINGS.get(r)]
    if not ranks or not WINGS_COORDS:
        return
    c = WINGS_COORDS
    if not _abrir_loja_com_confirmacao(c, "wing_shop", "pena_confirm", "pena.png"):
        return
    _clicar_vender(c, "wings")
    _clicar_vender(c, "buy")
    for rank in ranks:
        _clicar_vender(c, f"wing_{rank}")
    _clicar_vender(c, "buy_2")
    _clicar_vender(c, "confirm", 0.8)
    _clicar_vender(c, "ok", 0.8)
    _clicar_vender(c, "closer")
    _clicar_vender(c, "closer")   
    _clicar_vender(c, "wing_shop")

def vender_equipamento() -> None:
    """Mesma lógica do vender_wings, fluxo de Equipamento (forja/upgrade)."""
    ranks = [r for r in RANKS_ORDER if SELL_EQUIPMENT.get(r)]
    if not ranks or not EQUIP_COORDS:
        return
    c = EQUIP_COORDS
    if not _abrir_loja_com_confirmacao(c, "equip_forge", "forja_confirm", "forja.png"):
        return
    _clicar_vender(c, "upgrade")
    for rank in ranks:
        _clicar_vender(c, f"equip_{rank}")
    _clicar_vender(c, "confirm", 3.0)
    _clicar_vender(c, "closer")
    _clicar_vender(c, "closer")    
    _clicar_vender(c, "equip_forge")

def _aguardar_endless_e_clicar(timeout: float = 60) -> bool:
    """Espera language/pt-br/.../in_game/endless.png aparecer e clica (usado
    duas vezes: seleção do mapa e depois pra confirmar/entrar)."""
    started = time.time()
    while True:
        pos = locate("endless_ingame", "endless.png", confidence=0.75)
        if pos:
            click_pos(pos, delay_after=ENDLESS_CLICK_DELAY, rest=False)
            return True
        if time.time() - started > timeout:
            return False
        time.sleep(0.5)

ENDLESS_MAX_TENTATIVAS = 5

def _dog_templates() -> list[str]:
    """dog.png, dog_1.png, dog_2.png... - o texto do label não muda, mas a
    montaria embaixo é animada (pose diferente a cada captura), então um
    template só não bate sempre. Lista tudo que existir, na ordem."""
    paths = sorted(glob.glob(os.path.join(IMG_DIR, "dog*.png")))
    return [os.path.basename(p) for p in paths]

def _aguardar_dog_e_clicar(timeout: float = 3) -> bool:
    """Espera algum dog*.png (só o texto do label do Endless Trial no mapa)
    aparecer e clica abaixo dele, na montaria/npc - posição de clique fixa
    (coord) não funciona porque o mapa muda de lugar (bug do próprio jogo).
    Offset escala com o tamanho do template achado (locate_box), não é
    pixel fixo - acompanha resolução/zoom do mapa."""
    started = time.time()
    while True:
        for name in _dog_templates():
            box = locate_box("dog_ingame", name, confidence=0.75)
            if box:
                target = (box.left + box.width // 2, box.top + int(box.height * DOG_CLICK_Y_RATIO))
                click_pos(target, delay_after=ENDLESS_CLICK_DELAY, rest=False)
                return True
        if time.time() - started > timeout:
            return False
        time.sleep(0.5)

def ativar_endless() -> None:
    """3° fluxo (depois de equipamento/wings): entra no mapa Endless Trial -
    clica dog (template, posição varia - ver _aguardar_dog_e_clicar), espera
    endless.png aparecer e clica; se não aparecer (timeout), repete até
    ENDLESS_MAX_TENTATIVAS vezes. Depois aguarda 3s e dá 'd', espera
    endless.png aparecer de novo e clica - pronto."""
    if not ENDLESS:
        return
    hero = HERO_COORDS.get("hero")
    if hero:
        # 2 cliques separados em vez de doubleClick() - Dota às vezes não
        # reconhece o evento de double-click do SO (ver lobby.py).
        click_pos(hero, delay_after=0.15, rest=False)
        click_pos(hero, delay_after=ENDLESS_CLICK_DELAY, rest=False)
        if SLOT_20:
            try:
                pyautogui.press("f3")
                pyautogui.moveTo(*SLOT_20)
            except Exception:
                pass
    for _ in range(ENDLESS_MAX_TENTATIVAS):
        if _aguardar_dog_e_clicar() and _aguardar_endless_e_clicar(timeout=3):
            break
    time.sleep(3)
    try:
        pyautogui.press("d")
    except Exception:
        pass
    _aguardar_endless_e_clicar()

def aguardar_count_reaparecer(timeout: float = 60) -> bool:
    """Sincroniza a troca entre wings->equipamento: espera a tela voltar
    pro normal (count.png visível de novo) antes de abrir o próximo fluxo."""
    started = time.time()
    while True:
        if locate("count", "count.png", confidence=0.70):
            return True
        if time.time() - started > timeout:
            return False
        time.sleep(0.5)

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
    # enquanto espera a próxima partida começar (ver _bonus_watcher). Bonus
    # tem prioridade sobre tudo - roda solto em paralelo com a venda abaixo.
    threading.Thread(target=_bonus_watcher, daemon=True).start()

    # Venda: wings primeiro, depois equipamento - só entra na lista quem
    # tem pelo menos um rank marcado no painel "Vender" do start.py. Entre
    # um fluxo e outro espera count.png reaparecer (tela normalizou) antes
    # de abrir o próximo; se só um (ou nenhum) tá marcado não precisa
    # esperar nada extra.
    fluxos_venda = []
    if any(SELL_WINGS.get(r) for r in RANKS_ORDER):
        fluxos_venda.append(vender_wings)
    if any(SELL_EQUIPMENT.get(r) for r in RANKS_ORDER):
        fluxos_venda.append(vender_equipamento)
    if ENDLESS:
        fluxos_venda.append(ativar_endless)

    for i, fluxo in enumerate(fluxos_venda):
        if fluxo is ativar_endless:
            fluxo()
        else:
            _rodar_com_retry_bonus(fluxo)
        if i < len(fluxos_venda) - 1:
            aguardar_count_reaparecer()

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
