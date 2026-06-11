
# Bot Dota 2 - Auto Lobby & In-Game

Este é um script de automação em Python para gerenciar ciclos de partidas (Re-Host) no Dota 2. Ele gerencia o fluxo desde a abertura do jogo, inserção de senhas, busca de lobbies, interações in-game (coleta de bônus e evento da raposa) até o encerramento do jogo e reinicialização automática do ciclo.

## 🚀 Como fazer o projeto rodar do zero

Siga os passos abaixo após clonar o repositório em sua máquina:

### 1. Pré-requisitos
* Ter o **Python 3.10 ou superior** instalado no Windows.
* **IMPORTANTE:** Durante a instalação do Python, certifique-se de marcar a caixinha **"Add Python to PATH"** na primeira tela do instalador.

---

### 2. Instalação das Dependências

Para não precisar instalar módulo por módulo manualmente, o projeto já vem com um instalador automatizado.

1. Abra a pasta do projeto.
2. Dê um duplo clique no arquivo **`setup.bat`**.
3. Aguarde a janela do terminal terminar o processo e mostrar a mensagem `TUDO PRONTO!`.

> *O que o setup.bat faz por baixo dos panos? Ele atualiza o seu `pip` e instala o `pyautogui`, `keyboard` (para o botão de pânico ESC) e o `opencv-python` (necessário para a precisão das imagens).*

---

### 3. Configuração das Imagens
O script funciona com base no reconhecimento de tela. Certifique-se de que as pastas de imagens existam e contenham os prints corretos do seu jogo:
* **`img/`** -> Deve conter: `lista.png`, `image.png`, `lobby.png`, `ok.png`, `erro.png`, `aceitar.png`, `sala.png`, `game.png`, `att.png`, `200.png`.
* **`in_game/`** -> Deve conter: `bonus.png`, `trial.png`, `inicio_trial.png`, `confirm.png`, `fim_trial.png`, `count.png`, `dc2.png`, `dc3.png`, `fechar.png`, `sim.png`.

*Nota: O script foi calibrado originalmente para a resolução **1920x1080** com busca em tela cheia.*

---

### 4. Como Iniciar o Bot

O ponto de entrada principal do projeto é o arquivo **`start.py`** (responsável por gerenciar os ciclos globais). 

1. Abra o terminal (Prompt de Comando ou PowerShell) dentro da pasta do projeto.
2. Execute o comando principal:
   ```bash
   python start.py