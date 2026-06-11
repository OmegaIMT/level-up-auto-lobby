import os
import sys
import time
import threading
import subprocess
import pyautogui
import keyboard  # REQUISITO: pip install keyboard

# ==================================================
# CONFIGURAÇÕES E MEMÓRIA GLOBAL (PERSISTENTE)
# ==================================================

IMG_DIR = "in_game"

# Resgata os valores globais definidos no start.py ou mantidos no ambiente
RE_HOST_MAX = int(os.environ.get("RE_HOST_GLOBAL", "2"))

# PULO DO GATO: Resgata a contagem atual do ambiente do Windows (se não existir, começa em 0)
partidas_concluidas = int(os.environ.get("PARTIDAS_CONCLUIDAS_GLOBAL", "0"))

# Flags de controle locais da sessão atual
count_detectado = False

# Coordenadas fixas de suporte (Resolução 1920x1080)
COORDS = {
    "BONUS": (973, 797),
    "CENTRO_TELA": (960, 540),
    "DC_TOP_LEFT": (34, 28),     # Seta para voltar ao menu do Dota (topo esquerdo)
    "DC2_PADRAO": (1615, 965),    # Posição do primeiro botão vermelho (Desconectar)
    "DC3_PADRAO": (1615, 965),    # Posição do segundo botão vermelho (Sair da Partida)
    "FECHAR_PADRAO": (1883, 36), # Botão de desligar o Dota (topo direito)
    "SIM_PADRAO": (846, 594),    # Confirmação de saída
}

pyautogui.PAUSE = 0.1
pyautogui.FAILSAFE = True

# ==================================================
# FUNÇÃO DE PÂNICO (ESC)
# ==================================================

def verificar_esc():
    """Para o script imediatamente se o usuário apertar ESC."""
    keyboard.wait("esc")
    print("\n[AVISO] Execução interrompida pelo usuário via ESC!")
    os._exit(1)

# ==================================================
# HELPERS DE IMAGEM
# ==================================================

def img(nome):
    return os.path.join(IMG_DIR, nome)

def localizar(nome, confidence=0.85):
    try:
        return pyautogui.locateCenterOnScreen(img(nome), confidence=confidence)
    except Exception:
        return None

def clique_seguro(x, y, delay_depois=1.0):
    """Move o mouse, clica e espera o jogo processar a ação."""
    pyautogui.moveTo(x, y)
    time.sleep(0.2)
    pyautogui.click()
    time.sleep(delay_depois)

# ==================================================
# THREAD DE MONITORAMENTO DO COUNT (A CADA 7 SEGUNDOS)
# ==================================================

def monitorar_count_infinito():
    """Vigia o count.png. Se sumir, decide se reinicia o in_game ou fecha o jogo."""
    global count_detectado, partidas_concluidas
    
    print("[THREAD] Monitor de count.png iniciado (Ciclo: 7s).")
    
    while True:
        pos_count = localizar("count.png")
        
        # 1. Identificou o Count na tela
        if pos_count and not count_detectado:
            print("\a") 
            print("\n" + "#" * 60)
            print("[ALERTA VISUAL] !!! COUNT.PNG IDENTIFICADO COM SUCESSO !!!")
            print("#" * 60 + "\n")
            count_detectado = True
            
        # 2. O Count estava na tela e SUMIU (Rodada encerrada)
        elif not pos_count and count_detectado:
            partidas_concluidas += 1
            print(f"\n[VIGIA] count.png sumiu! Rodada concluída. ({partidas_concluidas}/{RE_HOST_MAX})")
            count_detectado = False 
            
            # DECISÃO DO FLUXO COM MEMÓRIA PERSISTENTE:
            if partidas_concluidas >= RE_HOST_MAX:
                print("[FLUXO] Limite alcançado! Zerando contador e fechando o Dota...")
                os.environ["PARTIDAS_CONCLUIDAS_GLOBAL"] = "0" # Reseta para o próximo ciclo do lobby
                fechar_e_desconectar_dota()
            else:
                print(f"[FLUXO] Salvando progresso ({partidas_concluidas}) e reiniciando in_game.py...")
                # Injeta o valor atualizado na memória do Windows antes de reiniciar
                os.environ["PARTIDAS_CONCLUIDAS_GLOBAL"] = str(partidas_concluidas)
                time.sleep(2.0)
                subprocess.Popen([sys.executable, "in_game.py"])
                os._exit(0)
            break
            
        time.sleep(7.0)

# ==================================================
# ETAPAS DO FLUXO DO JOGO
# ==================================================

def fase_inicial_partida():
    """Aguarda o carregamento inicial por até 3 minutos e checa o bônus."""
    print("[INFO] Procurando bônus inicial...")
    tempo_inicial = time.time()

    while (time.time() - tempo_inicial) < 180:  # 3 minutos
        bonus_pos = localizar("bonus.png")
        if bonus_pos:
            print("[OK] bonus.png encontrado! Clicando...")
            clique_seguro(*bonus_pos, delay_depois=0.5)
            break
        time.sleep(1)

    print("[INFO] Aguardando o count.png aparecer para rodar a raposa...")

def executar_evento_endless():
    """Faz a sequência de interação com a Raposa do Endless Trial."""
    print("[INFO] Executando sequência do Endless Trial...")

    raposa_pos = None
    for _ in range(20):  # Procura por até 10 segundos
        raposa_pos = localizar("trial.png", confidence=0.80)
        if raposa_pos:
            break
        time.sleep(0.5)

    if raposa_pos:
        print("[OK] Raposa encontrada! Clicando...")
        clique_seguro(*raposa_pos, delay_depois=0.5)
    else:
        print("[AVISO] Raposa não encontrada. Clicando no centro da tela...")
        clique_seguro(*COORDS["CENTRO_TELA"], delay_depois=0.5)

    time.sleep(1.0)
    inicio = localizar("inicio_trial.png")
    if inicio:
        clique_seguro(*inicio, delay_depois=0.5)

    time.sleep(0.5)
    confirm = localizar("confirm.png")
    if confirm:
        clique_seguro(*confirm, delay_depois=0.5)

    time.sleep(0.5)
    print("[INFO] Executando clique direito no centro da tela...")
    pyautogui.moveTo(*COORDS["CENTRO_TELA"])
    pyautogui.rightClick()

    print("[AGUARDANDO] Janela de fim_trial.png...")
    while True:
        fim = localizar("fim_trial.png")
        if fim:
            print("[OK] fim_trial encontrado.")
            confirm_fim = localizar("confirm.png")
            if confirm_fim:
                clique_seguro(*confirm_fim, delay_depois=0.5)
            else:
                clique_seguro(960, 750, delay_depois=0.5)
            break
        time.sleep(1)

# ==================================================
# FLUXO DE SAÍDA E FECHAMENTO
# ==================================================

def fechar_e_desconectar_dota():
    """Desconecta da partida, fecha o Dota e chama o lobby.py."""
    print("[INFO] Iniciando encerramento e saída do Dota 2...")

    print("[INFO] Clicando na seta para o menu principal...")
    clique_seguro(*COORDS["DC_TOP_LEFT"], delay_depois=1.5)

    print("[INFO] Procurando primeiro botão: Desconectar (dc2)...")
    pos_dc2 = localizar("dc2.png")
    if pos_dc2:
        clique_seguro(*pos_dc2, delay_depois=0.5)
    else:
        clique_seguro(*COORDS["DC2_PADRAO"], delay_depois=0.5)

    print("[INFO] Aguardando o botão de confirmação definitivo (dc3)...")
    pos_dc3 = None
    tempo_inicial = time.time()
    while (time.time() - tempo_inicial) < 15:
        pos_dc3 = localizar("dc3.png")
        if pos_dc3:
            break
        time.sleep(0.2)

    if pos_dc3:
        clique_seguro(*pos_dc3, delay_depois=2.5)  
    else:
        clique_seguro(*COORDS["DC3_PADRAO"], delay_depois=2.5)

    print("[INFO] Procurando botão de fechar o jogo (X)...")
    pos_fechar = localizar("fechar.png")
    if pos_fechar:
        clique_seguro(*pos_fechar, delay_depois=1.5)
    else:
        clique_seguro(*COORDS["FECHAR_PADRAO"], delay_depois=1.5)

    print("[INFO] Procurando botão de confirmação SIM...")
    pos_sim = localizar("sim.png")
    if pos_sim:
        clique_seguro(*pos_sim, delay_depois=1.5)
    else:
        clique_seguro(*COORDS["SIM_PADRAO"], delay_depois=1.5)

    print("[OK] Dota 2 fechado. Abrindo lobby.py...")
    pw_atual = os.environ.get("PW_GLOBAL", "")
    subprocess.Popen([sys.executable, "lobby.py", pw_atual])
    os._exit(0)

# ==================================================
# LOOP EXECUÇÃO PRINCIPAL
# ==================================================

def rodar_fluxo_principal():
    print(f"==================================================")
    print(f"[START] IN_GAME SIMPLIFICADO | RE-HOST: {partidas_concluidas}/{RE_HOST_MAX}")
    print(f"==================================================")

    # 1. Coleta o bônus de entrada
    fase_inicial_partida()

    # 2. Aguarda o sinal de que o count apareceu na tela
    while not count_detectado:
        time.sleep(0.5)

    # 3. Se o count apareceu, executa a raposa uma vez
    executar_evento_endless()
    
    # 4. Trava aqui e deixa a thread vigilante cuidar do sumiço do count e decidir o destino
    print("[STATUS] Sequência da Raposa feita. Deixando o monitor decidir o próximo passo...")
    while True:
        time.sleep(1.0)

if __name__ == "__main__":
    thread_panic = threading.Thread(target=verificar_esc, daemon=True)
    thread_panic.start()

    thread_vigia_count = threading.Thread(target=monitorar_count_infinito, daemon=True)
    thread_vigia_count.start()

    rodar_fluxo_principal()