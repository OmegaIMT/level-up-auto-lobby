import json
import os
import re
import subprocess
import sys
import threading
import time

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
POLL_FAST = 0.1  # polling reativo (aguardando aceitar/erro) — 33Hz era exagero pra UI, 12Hz já é bem mais rápido que reação humana e derruba CPU ~3x
POLL_NORMAL = 0.03  # polling padrão do loop de lobby
POLL_ATT = 0.05  # intervalo entre cliques no botão de atualizar
CLICK_PAUSE = 0.03  # pausa antes de cada clique
GAME_ENTER_PAUSE = 0.3  # pausa antes de cada clique ao entrar em game.png - precisa de mais tempo que CLICK_PAUSE pro Dota registrar hover na linha antes do click (ver comentário em step_lobby)
FOCUS_WAIT = 0.8  # tempo para o Windows processar foco
ATT_CYCLE_WAIT_NO_CACHE = 0.4  # janela total de espera após cada clique em ATT pra checar game.png (sem cache - ver locate_fresh)
ATT_CHECK_POLL = 0.2  # intervalo entre checagens de game.png dentro da janela acima - poll em vez de checar só uma vez no fim
MENU_STEP_WAIT = 0.25  # pausa entre cliques no menu (reduzida pela metade)
SAIR_TIMEOUT = 1.5  # timeout do popup opcional "sair" (reduzido pela metade)
SALA_TIMEOUT = (
    170  # sala.png travada (sem erro/aceitar) por mais que isso reinicia o dota
)
FIM_TIMEOUT = (
    360  # fim.png não aparece (aceitar travado) por mais que isso reinicia o dota
)
DOTA_OPEN_TIMEOUT = 180  # tempo max esperando a janela do Dota 2 aparecer após steam://run/570 (subiu de 90: PC/Steam lento perdia a janela)
DOTA_RETRY_INTERVAL = 10  # reenvia steam://run/570 se a janela ainda não apareceu (baixou de 15: mais tentativas dentro do timeout)
DOTA_UPDATE_TIMEOUT = 1800  # se o Steam estiver baixando atualização do Dota, estende a espera até isso (30min) em vez de desistir
DOTA_UPDATE_LOG_EVERY = 30  # a cada quantos s logar o progresso do update enquanto espera
MENU_STALL_TIMEOUT = 60  # step_menu sem achar lista.png/image.png por mais que isso: reabre o Dota
ADAPTIVE_DELAY_CAP = 3.0  # teto do buffer adaptativo abaixo, pra não herdar um travamento (ex: MENU_STALL_TIMEOUT) como espera

# ==================================================
# SESSION CONFIG (gerado pelo start.py)
# ==================================================
SESSION_CONFIG_FILE = sys.argv[1] if len(sys.argv) > 1 else "config.json"
STATUS_FILE = "status.json"  # status ao vivo, lido pelo painel.py
LOCK_FILE = "bot.lock"  # sentinela compartilhado com painel.py

# LOGS_DIR: pasta de log de texto - antes o log ia solto na raiz.
LOGS_DIR = "logs"
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, "lobby_log.txt")  # arquivo próprio (era bot_log.txt compartilhado) - console fica oculto (ShowWindow 0), sem isso print() não vai a lugar nenhum


def _log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _load_session_config() -> dict:
    """Lê o config.json gerado pelo start.py."""
    if os.path.exists(SESSION_CONFIG_FILE):
        try:
            with open(SESSION_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Erro ao ler {SESSION_CONFIG_FILE}: {e}")

    return {
        "passwords": "",
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
    "conexao_deadline": 0.0,
    # status: "buscando_sala" | "aguardando" | "conectando" | "em_partida" -
    # painel.py usa pra decidir o rótulo e se o campo "tempo" conta pra cima
    # (buscando_sala/aguardando/em_partida) ou pra baixo (conectando, mesmo
    # esquema de conexao_deadline). status_since é o timestamp de quando
    # ENTROU no status atual (ver _set_status) - só ele muda na transição,
    # não a cada tick, senão o crescente nunca sairia de 00:00.
    "status": "buscando_sala",
    "status_since": 0.0,
}


def save_status(
    partidas: int | None = None,
    rehost_max: int | None = None,
    ciclos: int | None = None,
    current_pw: str | None = None,
    password_deadline: float | None = None,
    current_image: str | None = None,
    image_found: bool | None = None,
    conexao_deadline: float | None = None,
    status: str | None = None,
    status_since: float | None = None,
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
        if conexao_deadline is not None:
            payload["conexao_deadline"] = conexao_deadline
        if status is not None:
            payload["status"] = status
        if status_since is not None:
            payload["status_since"] = status_since

        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Erro ao salvar {STATUS_FILE}: {e}")


# ==================================================
# STATS DA SESSÃO (resumo do ESC - ver resumo.py)
# ==================================================
STATS_FILE = "stats.json"
_stats_lock = threading.Lock()


def _stats_add(**deltas: float) -> None:
    """Soma cada valor em deltas ao respectivo campo em stats.json (merge -
    lê, soma, grava). Contador de sessão inteira, zerado só quando o usuário
    clica Iniciar (ver start.py/reset_stats)."""
    with _stats_lock:
        current: dict = {}
        if os.path.exists(STATS_FILE):
            try:
                with open(STATS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        current = loaded
            except Exception:
                pass
        for key, valor in deltas.items():
            current[key] = current.get(key, 0) + valor
        try:
            with open(STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ==================================================
# STATUS (buscando_sala / aguardando / conectando / em_partida)
# ==================================================
_status_atual: str | None = None
_status_since_local = 0.0


def _set_status(nome: str) -> None:
    """Só grava (e reseta status_since) quando o status muda de verdade -
    chamado toda iteração de alguns loops, então sem essa guarda o
    status_since seria resetado a cada tick e o "tempo" crescente do painel
    nunca sairia de 00:00. "em_partida" fica intacto por todo o ciclo
    (várias partidas via re-host) porque só o lobby.py chama _set_status -
    in_game.py/fim_game.py nunca tocam em "status"/"status_since" (só
    partidas/rehost_max/ciclos), e um lobby.py novo só sobe de novo quando o
    ciclo fecha ou dá erro (ver disconnect_and_relaunch nos outros dois
    arquivos) - é aí que volta pra "buscando_sala".

    Ao SAIR de "buscando_sala" soma o tempo gasto nela em
    stats.tempo_buscando_sala_total - é o único status que o lobby.py entra
    e sai várias vezes no mesmo processo (toda vez que uma sala falha volta
    pra cá), por isso acumula aqui em vez de num call site só."""
    global _status_atual, _status_since_local
    if _status_atual == nome:
        return
    agora = time.time()
    if _status_atual == "buscando_sala" and _status_since_local:
        _stats_add(tempo_buscando_sala_total=agora - _status_since_local)
    _status_atual = nome
    _status_since_local = agora
    save_status(status=nome, status_since=agora)


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

FILTRO = str(SESSION.get("filtro", "")).strip()  # texto digitado no campo de busca; vazio = pula filtro
try:
    CONEXAO_SEG = max(0.0, float(SESSION.get("conexao_min", 0)) * 60)
except (TypeError, ValueError):
    CONEXAO_SEG = 0.0  # tempo extra (campo "Conexão" do start.py, em minutos) somado após achar fim.png, antes de abrir o in_game - dá tempo do Dota terminar de conectar no servidor
REHOST_MAX: int = SESSION.get("rehost_max", 1)
LANGUAGE = SESSION.get("language", "pt-br")
RESOLUTION = SESSION.get("resolution", "1920x1080")

_IMG_DIR_WITH_RES = os.path.join("language", LANGUAGE, RESOLUTION, "lobby")
_IMG_DIR_NO_RES = os.path.join("language", LANGUAGE, "lobby")

IMG_DIR = _IMG_DIR_WITH_RES if os.path.exists(_IMG_DIR_WITH_RES) else _IMG_DIR_NO_RES

# GLOBAL_DIR: imagens idênticas nos 4 idiomas (sem texto localizado) vivem
# aqui uma vez só em vez de duplicadas em cada pasta de idioma - ver
# _img_path. Mesmo esquema do in_game.py/fim_game.py.
GLOBAL_DIR = os.path.join("language", "global", RESOLUTION, "lobby")

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
# lobbies desloca mais os itens, e uma janela fixa de 60px (base 1920x1080)
# errava o alvo com mais frequência, caindo no fallback de scan em tela
# cheia (bem mais caro em telas maiores).
try:
    _RES_WIDTH = int(RESOLUTION.lower().split("x")[0])
except Exception:
    _RES_WIDTH = 1920
CACHE_MARGIN = max(
    60, round(60 * _RES_WIDTH / 1920)
)  # px ao redor da coord salva para a região de busca rápida

def current_password() -> str:
    return PASSWORD_FIXED


# ==================================================
# BUFFER ADAPTATIVO (PC fraco)
# ==================================================
# Em PC fraco, a imagem já bateu (lista.png achado / ok.png sumido) mas a UI
# por trás pode ainda não estar pronta pra receber input - o campo de senha/
# filtro só ganha foco de verdade um pouco depois. Em vez de um sleep fixo
# que funciona na máquina do dev e falha na do usuário, usamos o próprio
# tempo que a transição anterior levou (quão devagar essa máquina está agora)
# como estimativa de quanto esperar antes de digitar.
_menu_render_delay = MENU_STEP_WAIT  # quanto lista.png demorou a aparecer - cruza step_menu -> step_password


def _elapsed_since(start: float) -> float:
    """Tempo decorrido desde `start`, limitado por ADAPTIVE_DELAY_CAP pra não
    herdar um travamento (ex: MENU_STALL_TIMEOUT) como buffer de espera."""
    return min(time.time() - start, ADAPTIVE_DELAY_CAP)


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
    exe_proprio = (
        os.path.basename(sys.executable).lower()
        if getattr(sys, "frozen", False)
        else None
    )
    alvos = [
        t
        for t in ("lobby.exe", "in_game.exe", "fim_game.exe", "painel.exe")
        if t != exe_proprio
    ]

    # Popen (sem esperar) em vez de run: os processos-alvo sobrevivem ao
    # pai no Windows, então não precisa bloquear aqui pra eles morrerem -
    # só disparar e sair rápido (esc não pode ter delay perceptível).
    # Um taskkill só com múltiplos /IM em vez de um por processo também
    # elimina overhead de spawn repetido.
    if alvos:
        try:
            args = ["taskkill", "/F"]
            for t in alvos:
                args += ["/IM", t]
            subprocess.Popen(
                args,
                startupinfo=HIDDEN_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    ps_script = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
        "Where-Object { $_.CommandLine -match 'lobby\\.py|in_game\\.py|fim_game\\.py|painel\\.py' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            startupinfo=HIDDEN_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ==================================================
# RESUMO DA SESSÃO (mostrado ao apertar ESC - ver resumo.py)
# ==================================================
ESC_LOCK_FILE = "esc_summary.lock"


def _tentar_gerar_resumo() -> bool:
    """lobby/in_game/fim_game/painel pegam o ESC quase ao mesmo tempo (cada
    um com seu próprio _watch_esc) - só UM deve fechar as stats e abrir o
    resumo. open(..., 'x') é atômico no SO: só o primeiro a chegar consegue
    criar o arquivo, os outros caem no FileExistsError e só seguem pro
    _matar_irmaos direto."""
    try:
        fd = os.open(ESC_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception:
        return True  # não devia falhar por outro motivo - na dúvida, gera


def _flush_stats_final() -> None:
    """Fecha o intervalo do status atual (buscando_sala/em_partida) em
    stats.json antes do resumo - senão o trecho entre a última transição e o
    ESC nunca entraria na contagem. Lê status.json direto (não o estado local
    deste processo) porque qualquer um dos 4 (lobby/in_game/fim_game/painel)
    pode ser o que ganha a corrida do ESC, inclusive durante "em_partida",
    que quem grava é o lobby.py mas quem tá vivo nesse momento é outro."""
    dados = _read_status_raw()
    estado = dados.get("status")
    desde = dados.get("status_since", 0.0)
    if not desde:
        return
    elapsed = time.time() - desde
    if estado == "buscando_sala":
        _stats_add(tempo_buscando_sala_total=elapsed)
    elif estado == "em_partida":
        _stats_add(tempo_em_partida_total=elapsed)


def _launch_resumo() -> None:
    try:
        if os.path.exists("resumo.exe"):
            subprocess.Popen(["resumo.exe"])
        elif os.path.exists("resumo.py"):
            subprocess.Popen([sys.executable, "resumo.py"])
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
    if _tentar_gerar_resumo():
        _flush_stats_final()
        _launch_resumo()
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
                f.writelines(f"{name}={cx},{cy}\n" for name, (cx, cy) in _coord_cache.items())
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
    # Se não existir na pasta do idioma, cai pro global (imagem idêntica nos
    # 4 idiomas, movida pra lá uma vez só - ver GLOBAL_DIR).
    caminho = os.path.join(IMG_DIR, name)
    if not os.path.exists(caminho):
        global_path = os.path.join(GLOBAL_DIR, name)
        if os.path.exists(global_path):
            return global_path
    return caminho


Region = tuple[int, int, int, int]


_ultima_excecao_locate: str | None = None
_ultima_excecao_locate_time = 0.0
EXCECAO_LOCATE_LOG_INTERVAL = 30.0  # throttle - erro real (ex: cv2 ausente) repete a cada poll, não spammar


def _locate_raw(
    name: str,
    confidence: float,
    region: Region | None = None,
) -> tuple[int, int] | None:
    global _ultima_excecao_locate, _ultima_excecao_locate_time
    try:
        return pyautogui.locateCenterOnScreen(
            _img_path(name),
            confidence=confidence,
            region=region,
        )
    except Exception as e:
        # ImageNotFoundException é o sinal NORMAL do pyautogui/pyscreeze pra
        # "não achou a imagem" (pyscreeze levanta exceção em vez de devolver
        # None por padrão) - não é erro, acontece toda busca que não bate
        # (ex: game.png antes do host iniciar a partida). Só loga exceções DE
        # VERDADE (cv2 ausente, imagem corrompida etc.) - mesmo fix do
        # in_game.py/fim_game.py.
        if type(e).__name__ != "ImageNotFoundException":
            msg = f"{name}: {type(e).__name__}: {e}"
            now = time.time()
            if msg != _ultima_excecao_locate or (now - _ultima_excecao_locate_time) > EXCECAO_LOCATE_LOG_INTERVAL:
                _ultima_excecao_locate = msg
                _ultima_excecao_locate_time = now
                _log(f"_locate_raw: EXCEÇÃO ao buscar imagem - {msg}")
        return None


def locate(name: str, confidence: float = 0.7) -> tuple[int, int] | None:
    """Usa a coordenada cacheada (se existir) pra restringir a busca a uma
    região pequena em volta da última posição achada - bem mais rápido que
    varrer a tela inteira. Se a região não bater (posição mudou, ou o
    template é maior que a margem e pyautogui reclama de "needle dimension(s)
    exceed the haystack" - erro real, não ImageNotFoundException, mas
    _locate_raw já trata como "não achou"), invalida o cache e cai pro scan
    de tela cheia - se auto-corrige."""
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


def locate_fresh(name: str, confidence: float = 0.7) -> tuple[int, int] | None:
    """locate() sem cache - sempre varre a tela inteira. Usado só no loop de
    ATT (_refresh_until_game_appears): game.png é a linha do lobby buscado,
    a posição muda a cada busca (nº de resultados, scroll) - uma coordenada
    cacheada de uma partida anterior aponta pra um lugar que pode não ter
    nada, e o bot fica clicando ATT sem nunca redetectar o jogo (era
    literalmente isso: coords/*_lobby.txt vem versionado com um game.png
    fixo, capturado numa busca específica, que não serve pra outra). att.png
    entra no mesmo bypass por rodar no mesmo loop - o resto do fluxo (menu,
    senha, sala) continua cacheado normalmente."""
    pos = _locate_raw(name, confidence)
    _update_debug(name, pos is not None)
    return pos


def wait_for(
    name: str,
    confidence: float = 0.7,
    timeout: float = 60,
) -> tuple[int, int] | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        pos = locate(name, confidence)
        if pos:
            return pos
        time.sleep(0.3)
    return None


def wait_disappear(
    name: str,
    confidence: float = 0.7,
    timeout: float = 60,
) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not locate(name, confidence):
            return True
        time.sleep(0.15)
    return False


def descansar_mouse() -> None:
    """Canto da tela, longe do botão clicado - mesmo esquema do in_game.py/
    fim_game.py. Usado depois de clicar aceitar.png: com o cursor em cima do
    botão às vezes dá pra confundir visualmente (e no screenshot) se ele
    sumiu de verdade ou só tá coberto pelo próprio mouse."""
    try:
        pyautogui.moveTo(20, 20)
    except Exception:
        pass


def safe_click(pos: tuple[int, int] | None, pause: float = CLICK_PAUSE, duration: float = 0.0) -> bool:
    if pos:
        # duration=0 teleporta o cursor (sem evento de mouse-move de verdade) -
        # em telas do Dota que exigem hover antes do click (ver comentário em
        # step_lobby, dois cliques em game.png), isso faz o clique "cair no
        # vazio". Callers que clicam em elementos sensíveis a hover (ex:
        # aceitar.png) devem passar duration>0.
        pyautogui.moveTo(pos[0], pos[1], duration=duration)
        time.sleep(pause)
        pyautogui.click()
        return True
    return False


# ==================================================
# GAME FLOW
# ==================================================
def _kill_dota() -> None:
    """Mata qualquer dota2.exe (inclusive um zumbi travado que impede o Steam
    de relançar)."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "dota2.exe"],
            startupinfo=HIDDEN_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _steam_path() -> str | None:
    """Pasta de instalação do Steam (registro, com fallback nos caminhos padrão)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            val, _ = winreg.QueryValueEx(k, "SteamPath")
            if val and os.path.isdir(val):
                return val
    except Exception:
        pass
    for p in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
        if os.path.isdir(p):
            return p
    return None


def _dota_appmanifest() -> str | None:
    """Caminho do appmanifest_570.acf do Dota, procurando em todas as bibliotecas
    Steam (libraryfolders.vdf). None se não achar."""
    steam = _steam_path()
    if not steam:
        return None
    libs = [steam]
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf, "r", encoding="utf-8", errors="ignore") as f:
            libs.extend(
                m.group(1).replace("\\\\", "\\")
                for m in re.finditer(r'"path"\s*"([^"]+)"', f.read())
            )
    except Exception:
        pass
    for lib in libs:
        manifest = os.path.join(lib, "steamapps", "appmanifest_570.acf")
        if os.path.exists(manifest):
            return manifest
    return None


def dota_update_pending() -> tuple[bool, int]:
    """(precisa_atualizar, pct_baixado) lendo o StateFlags do Steam.
    StateFlags == 4 → instalado e atualizado. Sem Steam/manifest → (False, 0),
    e o fluxo normal (timeout curto) segue como antes."""
    manifest = _dota_appmanifest()
    if not manifest:
        return False, 0
    try:
        with open(manifest, "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()
    except Exception:
        return False, 0

    def _num(key: str) -> int:
        m = re.search(rf'"{key}"\s*"(\d+)"', data)
        return int(m.group(1)) if m else 0

    if _num("StateFlags") == 4:  # StateFullyInstalled, nada pendente
        return False, 100
    to_dl = _num("BytesToDownload")
    dled = _num("BytesDownloaded")
    pct = int(dled * 100 / to_dl) if to_dl else 0
    return True, pct


def _launch_loop(timeout: float) -> bool:
    """Dispara steam://run/570 periodicamente até a janela do Dota aparecer ou
    estourar o timeout. Se detectar update baixando, estende o prazo até
    DOTA_UPDATE_TIMEOUT (Steam atualiza o Dota antes de abrir e isso leva minutos)."""
    deadline = time.time() + timeout
    last_launch = 0.0
    last_update_log = 0.0
    while time.time() < deadline:
        if time.time() - last_launch >= DOTA_RETRY_INTERVAL:
            try:
                subprocess.Popen(
                    ["cmd", "/c", "start", "steam://run/570"],
                    startupinfo=HIDDEN_WINDOW,
                )
            except Exception as e:
                _log(f"Erro ao disparar steam://run/570: {e}")
            last_launch = time.time()

        time.sleep(1.0)
        if focus_dota():
            return True

        pending, pct = dota_update_pending()
        if pending:
            deadline = max(deadline, time.time() + DOTA_UPDATE_TIMEOUT)
            if time.time() - last_update_log >= DOTA_UPDATE_LOG_EVERY:
                _log(f"Dota atualizando pelo Steam ({pct}% baixado) - aguardando update terminar")
                last_update_log = time.time()
    return False


def open_dota() -> bool:
    """Garante o Dota aberto e focado. Trata Steam lento, update em andamento e
    dota2.exe zumbi. Retorna True se a janela apareceu."""
    if focus_dota():
        return True

    _log("Janela do Dota 2 não encontrada, abrindo via steam://run/570")
    if _launch_loop(DOTA_OPEN_TIMEOUT):
        return True

    # timeout sem update em andamento: pode ter sobrado um dota2.exe travado
    # segurando o relançamento. Mata o resíduo e tenta mais uma rodada.
    _log(f"Timeout de {DOTA_OPEN_TIMEOUT}s - matando dota2.exe resíduo e tentando de novo")
    _kill_dota()
    time.sleep(4.0)
    if _launch_loop(DOTA_OPEN_TIMEOUT):
        return True

    _log("Timeout definitivo esperando a janela do Dota 2 abrir")
    return False


def step_up_name() -> None:
    buscar = wait_for("buscar.png", confidence=0.60, timeout=10)
    if not buscar:
        return

    safe_click(buscar, pause=0.3)
    time.sleep(0.4)

    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.05)
    pyautogui.press("delete")
    time.sleep(0.1)
    pyautogui.press("backspace", presses=10, interval=0.01)
    pyautogui.press("delete", presses=10, interval=0.01)
    time.sleep(0.3)

    pyautogui.write(FILTRO, interval=0.07)
    time.sleep(0.3)


def step_menu() -> None:
    global _menu_render_delay
    if not os.path.exists(IMG_DIR):
        os._exit(1)

    menu_start = time.time()
    stall_start = menu_start
    while True:
        focus_dota()

        if locate("lista.png"):
            break

        if safe_click(locate("image.png")):
            stall_start = time.time()

        if time.time() - stall_start > MENU_STALL_TIMEOUT:
            # focus_dota() sozinho NÃO abre o Dota - se a janela sumiu (crash,
            # fechou ou update), reabre de fato via open_dota. Sem isso o loop
            # ficava horas "refazendo fluxo completo" em cima de nada.
            if not focus_dota():
                _log("step_menu travado e janela do Dota sumiu - reabrindo o Dota")
                open_dota()
            else:
                _log("step_menu travado sem achar lista.png/image.png - refazendo fluxo completo")
            stall_start = time.time()
            menu_start = time.time()
            continue

        time.sleep(MENU_STEP_WAIT)

    # confirmado: lista.png visível - guarda quanto demorou pra aparecer,
    # usado mais adiante como buffer antes de digitar a senha.
    _menu_render_delay = _elapsed_since(menu_start)

    safe_click(locate("lista.png"))
    time.sleep(MENU_STEP_WAIT)

    sair = wait_for("sair.png", timeout=SAIR_TIMEOUT)
    if sair:
        safe_click(sair)
        wait_disappear("sair.png", timeout=SAIR_TIMEOUT)

    safe_click(wait_for("lobby.png"), pause=0.4)


def step_password() -> None:
    ok_pos = wait_for("ok.png")
    if not ok_pos:
        return

    time.sleep(max(_menu_render_delay, 0.3))
    focus_dota()
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("backspace")
    time.sleep(0.1)
    pyautogui.write(current_password(), interval=0.05)
    time.sleep(0.2)
    safe_click(ok_pos)
    time.sleep(0.3)


def _proceed_to_filter() -> None:
    """Espera ok.png sumir e digita o filtro. O tempo que ok.png levou pra
    sumir vira o buffer extra antes de digitar - mesma lógica do
    _menu_render_delay, pra PC lento não perder o campo de busca."""
    if not FILTRO:
        return

    disappear_start = time.time()
    wait_disappear("ok.png")

    time.sleep(max(_elapsed_since(disappear_start), 0.3))
    step_up_name()


def _launch_in_game() -> None:
    if os.path.exists("in_game.exe"):
        subprocess.Popen(["in_game.exe"], startupinfo=HIDDEN_WINDOW)
    elif os.path.exists("in_game.py"):
        subprocess.Popen([sys.executable, "in_game.py"], startupinfo=HIDDEN_WINDOW)


def _restart_dota() -> None:
    _kill_dota()
    time.sleep(4.0)
    open_dota()
    time.sleep(6.0)


def _restart_with_current_password() -> None:
    """Mata/abre o Dota e refaz o fluxo completo usando a senha fixa."""
    _restart_dota()
    step_menu()
    step_password()
    _proceed_to_filter()


# ==================================================
# PÓS-CLIQUE EM LOBBY
# ==================================================
def _accept_loop() -> bool:
    # CONEXAO_SEG (campo "Conexão" do start.py) SOMA no timeout de espera do
    # fim.png, não é buffer depois - dá mais tempo pro Dota terminar de
    # conectar antes de desistir e resetar. Achou fim.png -> lança o in_game
    # NA HORA, sem espera extra.
    timeout_total = FIM_TIMEOUT + CONEXAO_SEG
    start = time.time()
    while True:
        err = locate("erro.png")
        if err:
            _log("_accept_loop: erro.png apareceu depois do aceitar - clicando e abortando")
            safe_click(err)
            time.sleep(0.1)
            _stats_add(erros_conexao=1)
            return False

        # SÓ fim.png - fonte.png foi removido daqui: dava falso positivo logo
        # após clicar aceitar (batia em algo da tela de loading por engano),
        # fazendo o lobby encerrar e ir pra "em_partida" cedo demais, antes
        # de conectar de verdade.
        if locate("fim.png"):
            _log("_accept_loop: fim.png achado - conectado, entrando no jogo direto")
            save_status(conexao_deadline=0.0)
            _set_status("em_partida")
            _stats_add(salas_conectadas=1)
            _launch_in_game()
            return True

        if locate("sala.png"):
            _log("_accept_loop: voltou pra sala.png depois do aceitar (provável sala cheia) - abortando")
            _stats_add(erros_conexao=1)
            return False

        if time.time() - start > timeout_total:
            _log(f"_accept_loop: TIMEOUT ({timeout_total:.0f}s = FIM_TIMEOUT {FIM_TIMEOUT}s + conexao {CONEXAO_SEG:.0f}s) sem erro/fim/sala - abortando")
            _stats_add(erros_conexao=1)
            return False

        time.sleep(POLL_FAST)


# ==================================================
# LOOP DE ATT INTELIGENTE
# ==================================================
def _refresh_until_game_appears(max_attempts: int = 240) -> tuple[int, int] | None:
    """
    Clica em ATT enquanto uma thread separada procura game.png sem parar,
    em paralelo. Versão antiga (clicker/observer em threads) foi trocada por
    loop sequencial porque as duas threads brigavam pelo mouse (_mouse_lock)
    E pela mesma imagem ao mesmo tempo, perdendo sala.png na corrida - aqui
    só a busca roda em paralelo, quem clica (ATT/full.png) continua sendo só
    a thread principal, sem disputa de mouse. Motivo de voltar a paralelizar:
    o clique em ATT reseta/pisca a lista, e um poll preso ao ritmo do clique
    perde o instante exato em que game.png renderiza - a busca desacoplada do
    clique acha assim que aparece, não importa quem (bot ou o próprio usuário
    clicando por cima) estava batendo ATT.

    att.png/game.png usam locate_fresh (sem cache) - game.png é a linha do
    lobby buscado, muda de posição a cada busca, cache aqui fazia o bot ficar
    só atualizando sem nunca entrar (ver locate_fresh).
    """
    pos = locate_fresh("game.png", confidence=0.7)
    if pos:
        return pos

    att = locate_fresh("att.png")
    if not att:
        return None

    save_status(current_pw=current_password(), password_deadline=0.0)

    found: list[tuple[int, int] | None] = [None]
    stop_event = threading.Event()

    def _watch_game() -> None:
        while not stop_event.is_set():
            pos = locate_fresh("game.png", confidence=0.7)
            if pos:
                found[0] = pos
                stop_event.set()
                return
            time.sleep(ATT_CHECK_POLL)

    watcher = threading.Thread(target=_watch_game, daemon=True)
    watcher.start()

    try:
        for i in range(max_attempts):
            if stop_event.is_set():
                break

            safe_click(att, pause=POLL_ATT)
            time.sleep(ATT_CHECK_POLL)

            if stop_event.is_set():
                break

            # Se aparecer 'full.png' (sala cheia), clica pra fechar o aviso e segue.
            full_pop = locate("full.png", confidence=0.70)
            if full_pop:
                safe_click(full_pop, pause=0.1)
                time.sleep(0.2)

            # att.png não muda de posição dentro do loop (só entre resoluções
            # diferentes) - refazer o full-scan toda iteração é CPU jogada
            # fora, competindo com o watcher que precisa achar game.png rápido.
            # Reconfirma a cada 3 tentativas só pra cobrir o caso raro do
            # botão sumir/mudar (ex: popup por cima).
            if i % 3 == 0:
                att = locate_fresh("att.png") or att
    finally:
        stop_event.set()
        watcher.join(timeout=1.0)

    return found[0]


# ==================================================
# STEP LOBBY
# ==================================================
def step_lobby() -> None:
    if FILTRO:
        lobby_ready = wait_for("200.png", timeout=30)
        if not lobby_ready:
            safe_click(locate("att.png"))
            time.sleep(1.0)

    save_status(rehost_max=REHOST_MAX, current_pw=current_password())

    inside_room = False
    room_enter_time = 0.0

    while True:
        # ── ESTADO: dentro de uma sala ──────────────────────────────────────
        if inside_room:
            err = locate("erro.png")
            if err:
                _log("step_lobby: erro.png dentro da sala - reiniciando dota")
                safe_click(err, pause=0.1)
                time.sleep(0.2)
                _restart_with_current_password()
                inside_room = False
                continue

            aceitar = locate("aceitar.png")
            if aceitar:
                # mesmo motivo do duplo clique em game.png (ver step_lobby):
                # sem duration o cursor teleporta e o Dota não registra hover
                # antes do click, fazendo o "aceitar" às vezes não pegar.
                # Clica e reconfirma: se aceitar.png ainda estiver na tela, o
                # clique não pegou - clica de novo, SEM TETO, até sumir de
                # verdade (era limitado a ACCEPT_RETRIES tentativas e caía pro
                # _accept_loop mesmo com aceitar.png ainda óbvio na tela).
                _log("step_lobby: aceitar.png achado - clicando")
                # "conectando" começa aqui (achou aceitar) - deadline é o
                # mesmo teto de espera do _accept_loop (FIM_TIMEOUT +
                # CONEXAO_SEG, ver lá). Sem aperto depois: achou fim.png,
                # lança o in_game na hora.
                _set_status("conectando")
                save_status(conexao_deadline=time.time() + FIM_TIMEOUT + CONEXAO_SEG)
                tentativa = 0
                while aceitar:
                    tentativa += 1
                    safe_click(aceitar, pause=GAME_ENTER_PAUSE, duration=0.1)
                    descansar_mouse()
                    time.sleep(POLL_FAST)
                    aceitar = locate("aceitar.png")
                    if not aceitar:
                        _log(f"step_lobby: aceitar sumiu na tentativa {tentativa}")
                        break
                    _log(f"step_lobby: aceitar ainda na tela (tentativa {tentativa}) - clicando de novo")
                completed = _accept_loop()
                if completed:
                    return
                _log("step_lobby: aceitar falhou (ver motivo no _accept_loop acima) - reiniciando dota")
                _restart_with_current_password()
                inside_room = False
                continue

            if time.time() - room_enter_time > SALA_TIMEOUT:
                _log(f"step_lobby: SALA_TIMEOUT ({SALA_TIMEOUT}s) sem aceitar/erro - sala travada, reiniciando dota")
                _restart_with_current_password()
                inside_room = False
                continue

            time.sleep(POLL_FAST)
            continue

        # ── ESTADO: buscando lobby na lista ─────────────────────────────────
        _set_status("buscando_sala")

        err = locate("erro.png")
        if err:
            _log("step_lobby: erro.png na lista (fora da sala) - fechando e clicando ATT de novo")
            safe_click(err, pause=0.1)
            time.sleep(0.2)
            safe_click(locate("att.png"), pause=0.2)
            continue

        if locate("sala.png"):
            inside_room = True
            room_enter_time = time.time()
            _set_status("aguardando")
            _stats_add(salas_achadas=1)
            continue

        game = _refresh_until_game_appears()
        if not game:
            _log("240 tentativas de ATT sem achar game.png - refazendo fluxo completo (sair, senha, filtro)")
            focus_dota()
            step_menu()
            step_password()
            _proceed_to_filter()
            continue

        # Game encontrado → três cliques simples em sequência na posição já
        # capturada. pyautogui.doubleClick() manda um evento de double-click
        # de SO que o Dota às vezes não reconhece (mouse chega mas não entra
        # na sala) - cliques separados replicam o que já funcionava.
        # moveTo sem duration teleporta o cursor (sem evento de mouse-move de
        # verdade) e o CLICK_PAUSE de 0.03s some quase todo no overhead de
        # pyautogui.PAUSE - sobra ~0.008s real antes do clique, cedo demais
        # pro Dota registrar hover na linha antes do click (clica "no vazio").
        # Duration força movimento real; pausa maior antes do 1º clique dá
        # tempo do hover render. Do 2º ao 3º clique o hover já foi
        # registrado, então usa CLICK_PAUSE (bem mais apertado) só pra
        # garantir que o Dota separe os eventos - 3 cliques quase juntos
        # cobrem o caso de o 1º não pegar sem esperar outro ciclo de ATT.
        _log(f"step_lobby: game.png achado em {game} - 3 cliques pra entrar na sala")
        pyautogui.moveTo(game[0], game[1], duration=0.1)
        time.sleep(GAME_ENTER_PAUSE)
        pyautogui.click()
        time.sleep(CLICK_PAUSE)
        pyautogui.click()
        time.sleep(CLICK_PAUSE)
        pyautogui.click()

        inside_room = True
        room_enter_time = time.time()
        _set_status("aguardando")
        _stats_add(salas_achadas=1)


# ==================================================
# ENTRY POINT
# ==================================================
def main() -> None:
    threading.Thread(target=_watch_esc, daemon=True).start()
    _cache_load()

    # lobby.py só (re)inicia quando um ciclo fecha ou dá erro (ver
    # disconnect_and_relaunch em in_game.py/fim_game.py) - é exatamente onde
    # "em_partida" deve voltar a zero, então já entra aqui como
    # "buscando_sala" antes de qualquer outra coisa.
    _set_status("buscando_sala")

    open_dota()
    step_menu()
    step_password()
    _proceed_to_filter()
    step_lobby()

    _delete_lock()


if __name__ == "__main__":
    main()
