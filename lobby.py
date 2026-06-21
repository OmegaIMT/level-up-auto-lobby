import os
import sys
import time
import json
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
    kernel32 = ctypes.WinDLL('kernel32')
    user32   = ctypes.WinDLL('user32')
    hWnd = kernel32.GetConsoleWindow()
    if hWnd:
        user32.ShowWindow(hWnd, 0)

HIDDEN_WINDOW = subprocess.STARTUPINFO()
HIDDEN_WINDOW.dwFlags     |= subprocess.STARTF_USESHOWWINDOW
HIDDEN_WINDOW.wShowWindow  = 0

# ==================================================
# TIMING CONSTANTS
# ==================================================
POLL_FAST      = 0.03   # polling reativo (aguardando aceitar/erro)
POLL_NORMAL    = 0.03   # polling padrão do loop de lobby
POLL_ATT       = 0.02   # intervalo entre cliques no botão de atualizar
CLICK_PAUSE    = 0.03   # pausa antes de cada clique
FOCUS_WAIT     = 0.8    # tempo para o Windows processar foco
ATT_CYCLE_WAIT = 0.6    # espera após cada clique em ATT antes de checar
MENU_STEP_WAIT = 0.25   # pausa entre cliques no menu (era 0.5 — reduzida pela metade)
SAIR_TIMEOUT   = 1.5    # timeout do popup opcional "sair" (era 3 — reduzido pela metade)

# ==================================================
# SESSION CONFIG (gerado pelo start.py)
# ==================================================
SESSION_CONFIG_FILE = sys.argv[1] if len(sys.argv) > 1 else "config.json"
LOBBY_CONFIG_FILE    = "lobby_config.json"   # estado persistente do bot (senha que funcionou, coords)
STATUS_FILE          = "status.json"         # status ao vivo, lido pelo painel.py
LOCK_FILE            = "bot.lock"            # sentinela compartilhado com painel.py

UP_PREFIX = "up-"   # sempre digitado no campo de busca, no lugar do antigo lobby_name


def _load_session_config() -> dict:
    """
    Lê o config.json gerado pelo start.py.
    Mantém fallback em env vars / argv para compatibilidade, caso o arquivo
    não exista (execução manual do script, por exemplo).
    """
    if os.path.exists(SESSION_CONFIG_FILE):
        try:
            with open(SESSION_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Erro ao ler {SESSION_CONFIG_FILE}: {e}")

    # Fallback (compatibilidade com chamadas antigas)
    return {
        "passwords": [os.environ.get("PW_GLOBAL", sys.argv[2] if len(sys.argv) > 2 else "4433")],
        "password_interval_minutes": 1,
        "language": os.environ.get("LANGUAGE_GLOBAL", "pt-br"),
    }


def _load_lobby_state() -> dict:
    """Lê o estado persistente do bot (última senha que funcionou)."""
    if os.path.exists(LOBBY_CONFIG_FILE):
        try:
            with open(LOBBY_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_working_password": "", "last_working_index": -1}


def _save_lobby_state(state: dict) -> None:
    try:
        with open(LOBBY_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar {LOBBY_CONFIG_FILE}: {e}")


def _clear_lobby_state() -> None:
    """Reseta a senha salva e o índice em uso (chamado no ESC)."""
    _save_lobby_state({"last_working_password": "", "last_working_index": -1})


_status_lock = threading.Lock()


def _read_status_raw() -> dict:
    """Lê o status.json atual do disco, sem cache. Usado para merge em save_status."""
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
    """
    Atualiza o status.json lido pelo painel.py, fazendo MERGE com o que já
    está em disco — cada chamada só sobrescreve os campos que recebeu
    explicitamente (não-None), preservando os demais. Isso evita que uma
    atualização parcial (ex: só current_pw e deadline ao trocar de senha)
    apague campos como rehost_max que foram gravados em outro momento.

    password_deadline é um timestamp epoch (time.time()) marcando quando a
    troca de senha atual vai acontecer — o painel calcula a contagem
    regressiva localmente (deadline - now), sem depender de sincronizar
    contadores entre os dois processos.
    """
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
LOBBY_STATE = _load_lobby_state()

PASSWORDS: list[str] = [p for p in SESSION.get("passwords", []) if p] or ["4433"]
PASSWORD_INTERVAL_SECONDS: float = max(1, SESSION.get("password_interval_minutes", 1)) * 60
REHOST_MAX: int = SESSION.get("rehost_max", 1)
LANGUAGE = SESSION.get("language", "pt-br")
RESOLUTION = SESSION.get("resolution", "1920x1080")

_IMG_DIR_WITH_RES = os.path.join("language", LANGUAGE, RESOLUTION, "lobby")
_IMG_DIR_NO_RES    = os.path.join("language", LANGUAGE, "lobby")

# Preferimos a pasta com resolução (language/{idioma}/{resolução}/lobby).
# Se ela não existir no projeto, caímos para o formato antigo (sem resolução)
# para não quebrar instalações existentes.
IMG_DIR = _IMG_DIR_WITH_RES if os.path.exists(_IMG_DIR_WITH_RES) else _IMG_DIR_NO_RES

CACHE_FILE     = "coords_cache.txt"
CACHE_MARGIN   = 60     # px ao redor da coord salva para a região de busca rápida

# Se já existe uma senha marcada como "última que funcionou", começa por ela
_start_index = LOBBY_STATE.get("last_working_index", -1)
if 0 <= _start_index < len(PASSWORDS):
    _password_cursor = _start_index
else:
    _password_cursor = 0

_password_lock = threading.Lock()


def current_password() -> str:
    with _password_lock:
        return PASSWORDS[_password_cursor]


def advance_password() -> str:
    """Avança para a próxima senha da lista (round-robin) e retorna a nova senha."""
    global _password_cursor
    with _password_lock:
        _password_cursor = (_password_cursor + 1) % len(PASSWORDS)
        return PASSWORDS[_password_cursor]


def mark_password_working() -> None:
    """Salva a senha atual como a última que funcionou (chamado ao aceitar um lobby)."""
    with _password_lock:
        idx = _password_cursor
        pw = PASSWORDS[idx]
    _save_lobby_state({"last_working_password": pw, "last_working_index": idx})


def _delete_lock() -> None:
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass

# ==================================================
# PYAUTOGUI CONFIG
# ==================================================
pyautogui.PAUSE    = 0.02
pyautogui.FAILSAFE = True

# ==================================================
# EMERGENCY STOP (ESC)
# ==================================================
def _watch_esc() -> None:
    keyboard.wait("esc")
    _clear_lobby_state()
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
            user32.ShowWindow(hwnd, 9)       # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            time.sleep(FOCUS_WAIT)
            return True
    except Exception:
        pass
    return False

# ==================================================
# COORDINATE CACHE
# Formato do arquivo coords_cache.txt (uma entrada por linha):
#   nome_imagem:x:y
# Exemplo:
#   att.png:1200:122
#   lista.png:667:59
# ==================================================
_coord_cache: dict[str, tuple[int, int]] = {}

def _cache_load() -> None:
    """Carrega o cache do disco para memória ao iniciar."""
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
    """Persiste uma entrada no cache (reescreve o arquivo inteiro)."""
    _coord_cache[name] = (x, y)
    try:
        with open(CACHE_FILE, "w") as f:
            for k, (cx, cy) in _coord_cache.items():
                f.write(f"{k}:{cx}:{cy}\n")
    except Exception:
        pass

def _cache_invalidate(name: str) -> None:
    """Remove uma entrada do cache (a imagem mudou de posição ou sumiu)."""
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
    """Chamada direta ao pyautogui, sem cache."""
    try:
        return pyautogui.locateCenterOnScreen(
            _img_path(name),
            confidence=confidence,
            region=region,
        )
    except Exception:
        return None

def locate(name: str, confidence: float = 0.80) -> Optional[tuple[int, int]]:
    """
    Localiza a imagem usando coordinate cache.

    Fluxo:
      1. Se há coord salva → busca numa região mínima (CACHE_MARGIN px ao redor).
         Achou → retorna.  Não achou → invalida cache e vai para o passo 2.
      2. Busca full-screen.
         Achou → salva coord no cache e retorna.
         Não achou → retorna None.
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
        # Coord desatualizada → invalida e faz full-screen
        _cache_invalidate(name)

    # Full-screen scan
    pos = _locate_raw(name, confidence)
    if pos:
        _cache_save_entry(name, pos[0], pos[1])
    return pos

def wait_for(
    name: str,
    confidence: float = 0.80,
    timeout: float = 60,
) -> Optional[tuple[int, int]]:
    """Aguarda até `timeout` segundos que a imagem apareça."""
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
    """
    Digita o prefixo 'up-' no campo 'Buscar salas'.

    Antes dependia de um nome de lobby configurável; agora sempre apaga o
    que estiver no campo e digita o prefixo fixo UP_PREFIX ("up-").

    Na primeira execução: locate() faz full-screen scan com confidence=0.60
    (baixo para achar o campo mesmo com texto dentro) e salva a coord no cache.
    Nas próximas: vai direto na região salva — funciona em qualquer resolução
    pois a coord é aprendida na primeira vez, não hardcoded.
    """
    buscar = wait_for("buscar.png", confidence=0.60, timeout=10)
    if not buscar:
        return

    safe_click(buscar, pause=0.3)
    time.sleep(0.2)

    # Seleciona tudo e apaga — funciona com ou sem texto no campo
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.05)
    pyautogui.press("delete")
    time.sleep(0.1)

    pyautogui.write(UP_PREFIX, interval=0.05)
    time.sleep(0.3)   # aguarda a lista filtrar antes de ir para ATT

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

    # Opcional
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
    """Inicia o processo in_game após aceitar o lobby."""
    if os.path.exists("in_game.exe"):
        subprocess.Popen(["in_game.exe"], startupinfo=HIDDEN_WINDOW)
    elif os.path.exists("in_game.py"):
        subprocess.Popen([sys.executable, "in_game.py"], startupinfo=HIDDEN_WINDOW)

def _restart_dota() -> None:
    """Mata o Dota 2 e reabre via Steam."""
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


def _restart_with_next_password() -> None:
    """
    USADO SÓ EM ERRO DE VERDADE (erro.png detectado, falha após aceitar, etc).
    Avança para a próxima senha da lista, mata e reabre o Dota, e refaz o
    fluxo completo de entrada (menu → senha → prefixo up-).
    """
    advance_password()
    _restart_dota()
    step_menu()
    step_password()
    step_up_name()


def _retry_with_next_password() -> None:
    """
    USADO QUANDO SÓ ESGOTA O TEMPO DE BUSCA (sem erro nenhum no Dota).
    Não mata nem reabre o Dota — o jogo continua aberto, ainda na tela
    de lista de lobbies. Reclica em lobby.png (que reabre o popup de
    senha) e a partir daí repete o fluxo normal: step_password() para
    digitar a nova senha e step_up_name() para o prefixo de busca.
    """
    advance_password()
    safe_click(wait_for("lobby.png"), pause=0.4)
    step_password()
    step_up_name()

# ==================================================
# PÓS-CLIQUE EM LOBBY
# ==================================================
_ROOM_RESULT_SALA    = "sala"
_ROOM_RESULT_ACEITAR = "aceitar"
_ROOM_RESULT_ERRO    = "erro"

def _wait_after_room_click(timeout: float = 10) -> str:
    """
    Após o duplo-clique em um lobby, aguarda a resposta do Dota.

    Prioridade: erro > aceitar > sala
    Timeout → _ROOM_RESULT_ERRO (restart conservador)
    """
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
    """
    Loop reativo dentro de um lobby aguardando o jogo iniciar.

    Retorna True  → jogo iniciado (lançou in_game)
            False → erro detectado
    """
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
# LOOP DE ATT INTELIGENTE (clicker + observer em paralelo)
# ==================================================
def _refresh_until_game_appears(timeout_seconds: float) -> bool:
    """
    Clica em ATT continuamente numa thread enquanto outra thread fica
    só observando se game.png aparece — assim o clique nunca "rouba" o
    timeslice que seria usado pra perceber o game.png a tempo.

    Assim que o observer encontra game.png, sinaliza found_event e o
    clicker para imediatamente (sem esperar o próximo ciclo de sleep).

    Retorna True se game foi encontrado dentro do timeout, False caso
    o tempo se esgote (sinal para trocar de senha).
    """
    att = locate("att.png")
    if not att:
        return False

    deadline = time.time() + timeout_seconds
    save_status(current_pw=current_password(), password_deadline=deadline)

    found_event = threading.Event()
    stop_event = threading.Event()

    def _clicker() -> None:
        current_att = att
        while not stop_event.is_set() and not found_event.is_set():
            safe_click(current_att, pause=POLL_ATT)
            # espera curta e interrompível — não usamos time.sleep(ATT_CYCLE_WAIT)
            # "cru" pra não atrasar a reação ao found_event
            if found_event.wait(timeout=ATT_CYCLE_WAIT):
                return
            current_att = locate("att.png") or current_att

    def _observer() -> None:
        while not stop_event.is_set():
            if locate("game.png", confidence=0.90):
                found_event.set()
                return
            time.sleep(POLL_FAST)

    clicker_thread = threading.Thread(target=_clicker, daemon=True)
    observer_thread = threading.Thread(target=_observer, daemon=True)
    clicker_thread.start()
    observer_thread.start()

    found = found_event.wait(timeout=timeout_seconds)
    stop_event.set()
    clicker_thread.join(timeout=2)
    observer_thread.join(timeout=2)

    return found

# ==================================================
# STEP LOBBY
# ==================================================
def step_lobby() -> None:
    """
    Loop principal de busca de lobby.

    Estados:
      searching → procurando o lobby na lista
      inside    → dentro da sala, aguardando aceitar/fim

    Troca de senha:
      - Se o intervalo de troca se esgota SEM achar sala (clicando em ATT),
        NÃO reinicia o Dota: apenas avança para a próxima senha e repete
        step_password() + step_up_name() (_retry_with_next_password).
      - Se um ERRO de verdade é detectado (erro.png, falha após aceitar),
        avança a senha E reinicia o Dota (_restart_with_next_password).
      Ao aceitar um lobby com sucesso, a senha atual é salva como
      "última que funcionou" em lobby_config.json.
    """
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
                _restart_with_next_password()
                inside_room = False
                continue

            aceitar = locate("aceitar.png")
            if aceitar:
                safe_click(aceitar)
                mark_password_working()
                completed = _accept_loop()
                if completed:
                    return
                _restart_with_next_password()
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

        game_found = _refresh_until_game_appears(timeout_seconds=PASSWORD_INTERVAL_SECONDS)

        if not game_found:
            # Esgotou o intervalo de senha sem achar sala — NÃO é erro,
            # o Dota continua aberto. Só troca a senha no campo e segue
            # clicando em ATT/buscando.
            _retry_with_next_password()
            continue

        # Game encontrado → duplo-clique
        game = locate("game.png", confidence=0.90)
        if not game:
            continue

        pyautogui.moveTo(game[0], game[1])
        time.sleep(CLICK_PAUSE)
        pyautogui.doubleClick()

        result = _wait_after_room_click(timeout=10)

        if result == _ROOM_RESULT_ERRO:
            safe_click(locate("erro.png"), pause=0.1)
            _restart_with_next_password()

        elif result == _ROOM_RESULT_SALA:
            inside_room = True

        elif result == _ROOM_RESULT_ACEITAR:
            aceitar = locate("aceitar.png")
            if aceitar:
                safe_click(aceitar)
                mark_password_working()
                completed = _accept_loop()
                if completed:
                    return
                _restart_with_next_password()

# ==================================================
# ENTRY POINT
# ==================================================
def main() -> None:
    threading.Thread(target=_watch_esc, daemon=True).start()
    _cache_load()

    open_dota()
    step_menu()
    step_password()
    step_up_name()   # após a senha — campo de busca já está disponível
    step_lobby()

    _delete_lock()

if __name__ == "__main__":
    main()