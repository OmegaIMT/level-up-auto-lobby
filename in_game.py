import os
import sys
import time
import threading
import subprocess
import pyautogui
import keyboard

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
# CONFIG
# ==================================================
IMG_DIR      = "in_game"
REHOST_MAX   = int(os.environ.get("RE_HOST_GLOBAL", "2"))
CICLOS_FEITOS        = int(os.environ.get("CICLOS_GLOBAL", "0"))
PARTIDAS_CONCLUIDAS  = int(os.environ.get("PARTIDAS_CONCLUIDAS_GLOBAL", "0"))

# Timeout: se o count NÃO aparecer em X segundos → host saiu antes da partida começar
TIMEOUT_SEM_COUNT = 4800   # 1h20min

COORDS = {
    "DC_TOP_LEFT":   (34, 28),
    "DC2_PADRAO":    (1615, 965),
    "DC3_PADRAO":    (1615, 965),
    "FECHAR_PADRAO": (1883, 36),
    "SIM_PADRAO":    (846, 594),
}

POLL_IN_GAME = 2.0

pyautogui.PAUSE    = 0.1
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
# IMAGE HELPERS
# ==================================================
def locate(name: str, confidence: float = 0.85):
    try:
        return pyautogui.locateCenterOnScreen(
            os.path.join(IMG_DIR, name), confidence=confidence
        )
    except Exception:
        return None

def safe_click(x: int, y: int, delay_after: float = 1.0) -> None:
    pyautogui.moveTo(x, y)
    time.sleep(0.2)
    pyautogui.click()
    time.sleep(delay_after)

def click_pos(pos, delay_after: float = 1.0) -> None:
    safe_click(pos[0], pos[1], delay_after)

# ==================================================
# DISCONNECT & RELAUNCH LOBBY
# ==================================================
def disconnect_and_relaunch() -> None:
    """Desconecta da partida, fecha o Dota e relança o lobby."""
    safe_click(*COORDS["DC_TOP_LEFT"], delay_after=1.5)

    pos_dc2 = locate("dc2.png")
    if pos_dc2:
        click_pos(pos_dc2, delay_after=0.5)
    else:
        safe_click(*COORDS["DC2_PADRAO"], delay_after=0.5)

    pos_dc3 = None
    deadline = time.time() + 15
    while time.time() < deadline:
        pos_dc3 = locate("dc3.png")
        if pos_dc3:
            break
        time.sleep(0.2)

    if pos_dc3:
        click_pos(pos_dc3, delay_after=2.5)
    else:
        safe_click(*COORDS["DC3_PADRAO"], delay_after=2.5)

    pos_fechar = locate("fechar.png")
    if pos_fechar:
        click_pos(pos_fechar, delay_after=1.5)
    else:
        safe_click(*COORDS["FECHAR_PADRAO"], delay_after=1.5)

    pos_sim = locate("sim.png")
    if pos_sim:
        click_pos(pos_sim, delay_after=1.5)
    else:
        safe_click(*COORDS["SIM_PADRAO"], delay_after=1.5)

    pw_atual = os.environ.get("PW_GLOBAL", "")
    if os.path.exists("lobby.exe"):
        subprocess.Popen(["lobby.exe", pw_atual], startupinfo=HIDDEN_WINDOW)
    else:
        subprocess.Popen([sys.executable, "lobby.py", pw_atual], startupinfo=HIDDEN_WINDOW)

    os._exit(0)

# ==================================================
# BONUS CHECK
# ==================================================
def check_bonus() -> bool:
    for _ in range(4):
        pos = locate("bonus.png")
        if pos:
            click_pos(pos, delay_after=1.0)
            # Move para o centro da tela para não obstruir a visão do jogo
            cx = pyautogui.size().width  // 2
            cy = pyautogui.size().height // 2
            pyautogui.moveTo(cx, cy)
            return True
        time.sleep(15.0)
    return False

# ==================================================
# MAIN MONITOR
# ==================================================
def monitor_match() -> None:
    """
    Monitora count.png durante a partida.

    Regra de contagem:
      Incrementa PARTIDAS_CONCLUIDAS quando o count APARECE (partida começou).

    Fluxo ao atingir REHOST_MAX:
      count aparece → conta → limite atingido → zera partidas, incrementa ciclo
      → sai do Dota IMEDIATAMENTE via disconnect_and_relaunch(), sem esperar sumir.

    Fluxo normal (dentro do ciclo):
      count aparece → conta → aguarda count sumir → relança in_game.

    Timeout:
      count nunca aparece por TIMEOUT_SEM_COUNT segundos → host saiu → relaunch.
    """
    global PARTIDAS_CONCLUIDAS, CICLOS_FEITOS

    count_ever_seen = False
    count_visible   = False
    last_seen_time  = time.time()

    while True:
        pos_count = locate("count.png")

        if pos_count:
            # ── Count visível ───────────────────────────────────────────────
            if not count_ever_seen:
                # Primeira detecção → conta a partida agora
                count_ever_seen = True
                print("\a")

                PARTIDAS_CONCLUIDAS += 1
                save_status(PARTIDAS_CONCLUIDAS, REHOST_MAX, CICLOS_FEITOS)

                if PARTIDAS_CONCLUIDAS >= REHOST_MAX:
                    # Limite atingido → zera ciclo e sai AGORA, sem esperar o count sumir
                    CICLOS_FEITOS += 1
                    os.environ["CICLOS_GLOBAL"] = str(CICLOS_FEITOS)
                    os.environ["PARTIDAS_CONCLUIDAS_GLOBAL"] = "0"
                    save_status(0, REHOST_MAX, CICLOS_FEITOS)
                    disconnect_and_relaunch()
                    return

                # Ainda dentro do ciclo → atualiza env e continua monitorando
                os.environ["PARTIDAS_CONCLUIDAS_GLOBAL"] = str(PARTIDAS_CONCLUIDAS)

            count_visible  = True
            last_seen_time = time.time()

        else:
            # ── Count não visível ───────────────────────────────────────────
            tempo_sem_count = time.time() - last_seen_time

            if count_visible:
                # Count sumiu → partida encerrada dentro do ciclo → relança in_game
                count_visible = False
                time.sleep(2.0)
                if os.path.exists("in_game.exe"):
                    subprocess.Popen(["in_game.exe"], startupinfo=HIDDEN_WINDOW)
                else:
                    subprocess.Popen([sys.executable, "in_game.py"], startupinfo=HIDDEN_WINDOW)
                os._exit(0)

            elif not count_ever_seen and tempo_sem_count > TIMEOUT_SEM_COUNT:
                # Count nunca apareceu → host saiu antes de começar
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

    save_status(PARTIDAS_CONCLUIDAS, REHOST_MAX, CICLOS_FEITOS)

    check_bonus()
    monitor_match()