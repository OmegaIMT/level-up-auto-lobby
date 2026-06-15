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

LANGUAGE = os.environ.get("LANGUAGE_GLOBAL", "pt-br")

IMG_DIR = os.path.join(
    "language",
    LANGUAGE,
    "lobby"
)
CACHE_FILE     = "coords_cache.txt"
CACHE_MARGIN   = 60     # px ao redor da coord salva para a região de busca rápida

PW         = os.environ.get("PW_GLOBAL",         sys.argv[1] if len(sys.argv) > 1 else "4433")
LOBBY_NAME = os.environ.get("LOBBY_NAME_GLOBAL", sys.argv[2] if len(sys.argv) > 2 else "")
LOCK_FILE  = "bot.lock"   # sentinela compartilhado com painel.py

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
    timeout: int = 60,
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

def step_lobby_name() -> None:
    """
    Digita o nome do lobby no campo 'Buscar salas'.

    Na primeira execução: locate() faz full-screen scan com confidence=0.60
    (baixo para achar o campo mesmo com texto dentro) e salva a coord no cache.
    Nas próximas: vai direto na região salva — funciona em qualquer resolução
    pois a coord é aprendida na primeira vez, não hardcoded.
    """
    if not LOBBY_NAME:
        return

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

    pyautogui.write(LOBBY_NAME, interval=0.05)
    time.sleep(0.3)   # aguarda a lista filtrar antes de ir para ATT

def step_menu() -> None:
    if not os.path.exists(IMG_DIR):
        os._exit(1)

    while True:
        focus_dota()

        if locate("lista.png"):
            break

        safe_click(locate("image.png"))
        time.sleep(0.5)

    safe_click(locate("lista.png"))
    time.sleep(0.5)

    # Opcional
    sair = wait_for("sair.png", timeout=3)

    if sair:
        safe_click(sair)
        time.sleep(0.5)

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
    pyautogui.write(PW, interval=0.05)
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

# ==================================================
# PÓS-CLIQUE EM LOBBY
# ==================================================
_ROOM_RESULT_SALA    = "sala"
_ROOM_RESULT_ACEITAR = "aceitar"
_ROOM_RESULT_ERRO    = "erro"

def _wait_after_room_click(timeout: int = 10) -> str:
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
# LOOP DE ATT INTELIGENTE
# ==================================================
def _refresh_until_game_appears(max_attempts: int = 60) -> bool:
    """
    Clica em ATT e verifica se game.png aparece.
    O locate() já usa cache internamente — full-screen só na primeira vez.

    Retorna True se game foi encontrado, False se esgotou tentativas.
    """
    att = locate("att.png")
    if not att:
        return False

    for _ in range(max_attempts):
        safe_click(att, pause=POLL_ATT)
        time.sleep(ATT_CYCLE_WAIT)

        if locate("game.png", confidence=0.90):
            return True

        att = locate("att.png") or att

    return False

# ==================================================
# STEP LOBBY
# ==================================================
def step_lobby() -> None:
    """
    Loop principal de busca de lobby.

    Estados:
      searching → procurando o lobby na lista
      inside    → dentro da sala, aguardando aceitar/fim
    """
    lobby_ready = wait_for("200.png", timeout=30)
    if not lobby_ready:
        safe_click(locate("att.png"))
        time.sleep(1.0)

    inside_room = False

    while True:

        # ── ESTADO: dentro de uma sala ──────────────────────────────────────
        if inside_room:
            err = locate("erro.png")
            if err:
                safe_click(err, pause=0.1)
                time.sleep(0.2)
                _restart_dota()
                step_menu()
                step_password()
                step_lobby_name()
                inside_room = False
                continue

            aceitar = locate("aceitar.png")
            if aceitar:
                safe_click(aceitar)
                completed = _accept_loop()
                if completed:
                    return
                _restart_dota()
                step_menu()
                step_password()
                step_lobby_name()
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

        game_found = _refresh_until_game_appears(max_attempts=60)

        if not game_found:
            time.sleep(POLL_NORMAL)
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
            _restart_dota()
            step_menu()
            step_password()
            step_lobby_name()

        elif result == _ROOM_RESULT_SALA:
            inside_room = True

        elif result == _ROOM_RESULT_ACEITAR:
            aceitar = locate("aceitar.png")
            if aceitar:
                safe_click(aceitar)
                completed = _accept_loop()
                if completed:
                    return
                _restart_dota()
                step_menu()
                step_password()
                step_lobby_name()

# ==================================================
# ENTRY POINT
# ==================================================
def main() -> None:
    threading.Thread(target=_watch_esc, daemon=True).start()
    _cache_load()

    open_dota()
    step_menu()
    step_password()
    step_lobby_name()   # após a senha — campo de busca já está disponível
    step_lobby()

    _delete_lock()

if __name__ == "__main__":
    main()