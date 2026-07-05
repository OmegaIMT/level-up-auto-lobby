import sys
import os
import json
import time
import ctypes
import pyautogui
from datetime import datetime

# ==================================================
# Captura de coordenadas fixas via clique do mouse.
# Rode este script, clique nos campos pedidos no terminal, e ele gera
# um coords_base.json com todas as posições (capturadas na resolução
# atual da sua tela) pra depois o in_game.py escalar conforme precisar.
# ==================================================

if sys.platform != "win32":
    print("Este script usa GetAsyncKeyState do Windows, só funciona no Windows.")
    sys.exit(1)

user32 = ctypes.WinDLL("user32")
VK_LBUTTON = 0x01
VK_ESC     = 0x1B

OUTPUT_FILE = "coords_base.json"

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def mouse_button_down() -> bool:
    return (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0

def key_down(vk_code: int) -> bool:
    return (user32.GetAsyncKeyState(vk_code) & 0x8000) != 0

def wait_for_click(label: str):
    """
    Espera o próximo clique esquerdo do mouse.
    Retorna (x, y) com a posição capturada, ou None se o usuário apertar ESC (pular).
    Levanta KeyboardInterrupt se o usuário apertar Q (encerra tudo).
    """
    print()
    log(f"Posicione o mouse sobre '{label}' e clique com o botão ESQUERDO.")
    log("   (ESC = pular este campo | Q = encerrar e salvar o que já foi capturado)")

    # espera soltar o botão antes de começar, evita herdar um clique anterior
    while mouse_button_down():
        time.sleep(0.02)

    while True:
        if mouse_button_down():
            x, y = pyautogui.position()
            while mouse_button_down():
                time.sleep(0.02)
            return (x, y)

        if key_down(VK_ESC):
            log(f"'{label}' pulado.")
            return None

        if key_down(ord("Q")):
            log("Encerrando captura antecipadamente.")
            raise KeyboardInterrupt

        time.sleep(0.02)

def main() -> None:
    largura, altura = pyautogui.size()
    log(f"Resolução detectada da tela: {largura}x{altura}")

    labels = ["no_xp", "public_backpack_target"] + [f"slot_{i:02d}" for i in range(1, 25)]

    resultado = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                resultado = json.load(f)
            log(f"{OUTPUT_FILE} já existia, carregado com {len(resultado)} entrada(s). "
                f"Campos já preenchidos serão sobrescritos se você clicar de novo neles.")
        except Exception as e:
            log(f"Não foi possível ler {OUTPUT_FILE} existente, começando do zero: {e}")

    try:
        for label in labels:
            pos = wait_for_click(label)
            if pos is not None:
                resultado[label] = list(pos)
                log(f"'{label}' salvo em {pos}.")
    except KeyboardInterrupt:
        pass

    resultado["captured_resolution"] = f"{largura}x{altura}"

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    log(f"Captura finalizada. {len(resultado)} entrada(s) salva(s) em {OUTPUT_FILE}.")

if __name__ == "__main__":
    main()