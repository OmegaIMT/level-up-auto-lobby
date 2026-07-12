# Auto Lobby Level Up — Bot Dota 2

Automação em Python para farmar ciclos de partida (Re-Host) no Dota 2: abre o jogo, digita a senha, entra na lobby certa, aguarda a partida, coleta bônus/tesouros/evento durante o jogo e reinicia o ciclo sozinho.

## Arquitetura

O bot é dividido em processos independentes, cada um lançado pelo anterior:

| Arquivo | Papel |
|---|---|
| `start.py` | GUI (Tkinter) de configuração. Salva `config.json`, checa update no GitHub e lança `lobby.py`/`painel.py`. É o **único** que roda como `.exe`. |
| `lobby.py` | Abre o Dota, digita senha, busca a sala pelo prefixo `up-`, entra na partida e lança `in_game.py`. |
| `in_game.py` | Roda durante a partida: desativa XP, coleta bônus/tesouro, organiza mochila, dispara o evento e monitora o fim da partida (`count.png`). Ao detectar o fim, lança `fim_game.py` e encerra. |
| `fim_game.py` | Roda entre partidas: conta a partida e ciclos, cuida do banner de bonus (clica em loop se ainda tem próxima partida; espera e clica uma vez antes de fechar se é a última do ciclo) e decide entre fechar o Dota + voltar pro `lobby.py` ou lançar `in_game.py` de novo. |
| `painel.py` | Overlay transparente e click-through no canto da tela mostrando `partidas/rehost`, `ciclos` e a última imagem buscada (debug ao vivo). |
| `updater.py` | Auto-update via git (raw `version.txt` + zipball da branch `main`), sem precisar de Release nem rebuild. |
| `coord_capture.py` | Ferramenta manual (roda à parte, não entra no build) pra capturar coordenadas de clique via overlay + hotkey (F8 captura, F9 pula, ESC salva e sai) e gerar `coords/coords_base_vender.json`. |
| `build.py` + `build.spec` | Empacota `start.py`/`in_game.py`/`fim_game.py`/`lobby.py`/`painel.py` em `.exe` via PyInstaller e copia `language/`/`coords/`/etc pra raiz do `dist/`. |

`lobby.py`, `in_game.py` e `painel.py` de propósito **não** viram `.exe` — rodam sempre como script (`python lobby.py`), lançados pelo `start.exe` via `subprocess`. Isso é o que permite o `updater.py` atualizar o comportamento do bot só dando `git push`, sem rebuildar nem gerar instalador de novo (ver seção "Release / auto-update").

Toda a automação de tela funciona por **reconhecimento de imagem** (`pyautogui.locateOnScreen`), não por memory-reading nem OCR. As imagens de referência ficam em:

```
language/<idioma>/<resolução>/lobby/    # telas de menu e senha (dependem de idioma)
language/<idioma>/<resolução>/in_game/  # bonus/contagem (dependem de idioma)
language/global/<resolução>/suporte/    # itens, tesouro (independem de idioma)
language/global/<resolução>/event/      # evento
language/global/<resolução>/error/      # telas de erro/desconexão
```

Idiomas disponíveis: `pt-br`, `en-us`, `ru`, `zh-cn`. Resoluções calibradas: `1920x1080` e `1600x900`.

Coordenadas de clique fixo (mochila, status, gold) ficam em `coords/coords_base_in_game.json` (usado só pelo `in_game.py`) e `coords/coords_base_fim_game.json` (usado só pelo `fim_game.py`), cada bloco chaveado só pela resolução (ex: `"1920x1080"`) e escalado em runtime. Dota renderiza em pixels reais e não segue a escala de exibição do Windows (100%/125%/...), então a mesma resolução sempre cai na mesma coordenada, independente do zoom do sistema. A pasta `coords/` também guarda o cache de posição das imagens (um arquivo por resolução e por processo — `..._in_game.txt`, `..._fim_game.txt`, `..._lobby.txt` — versionado, mesma resolução sempre acha a imagem no mesmo lugar).

## Pré-requisitos

* Windows + Python 3.10 ou superior, com **"Add Python to PATH"** marcado na instalação.
* Dota 2 instalado (via Steam).

## Instalação

```bash
utilidades\setup.bat
```

Isso atualiza o `pip` e instala tudo do `utilidades/requirements.txt` (`pyautogui`, `opencv-python` — este último é exigido pelo `pyautogui` para o parâmetro `confidence` de matching por template).

## Como rodar

```bash
python start.py
```

Na janela: informa a senha da lobby, quantidade de re-hosts, idioma, resolução e as opções (Cristal, Equipamentos, Desativar XP, Suporte). Clicar em **Start** minimiza a janela e sobe `lobby.py` + `painel.py` em background.

**ESC** a qualquer momento mata o bot (todos os processos filhos).

## Build (gerar .exe)

```bash
python build.py
```

Roda o PyInstaller com `build.spec` (só `start.exe`) e copia `lobby.py`, `in_game.py`, `painel.py`, `updater.py`, `coords/`, `version.json`, `level-up.ico` e `language/` pra raiz de `dist/Dota-level-up-lobby/` (`requirements.txt` é só de dev — as dependências já vão embutidas no `.exe` pelo PyInstaller).

## Instalador (Setup.exe)

Requer [Inno Setup](https://jrsoftware.org/isinfo.php) instalado (`ISCC.exe`).

```bash
python build.py
"C:\Program Files\Inno Setup 7\ISCC.exe" installer.iss
```

Gera `installer_output/Dota-Level-Up-Lobby-Setup-<versão>.exe`. O instalador deixa o usuário escolher a pasta de destino, com padrão `C:\Dota Level Up Auto Lobby`.

## Release / auto-update

O `updater.py` compara o `version.txt` local com o `version.txt` da branch `main` no GitHub (via `raw.githubusercontent.com`). Pra publicar uma atualização:

1. Mexer no que precisar (`lobby.py`, `in_game.py`, `fim_game.py`, `painel.py`, imagens em `language/`, `coords/coords_base_in_game.json`, `coords/coords_base_fim_game.json`, etc).
2. Subir a versão em `version.txt` (ex: `2.2.0` -> `2.2.1`).
3. `git push` pra `main`.

No próximo boot do `start.exe` em qualquer máquina, ele detecta a versão nova, baixa o repo (zipball) e sobrescreve só os arquivos de código/dados — nunca `config.json`, `status.json`, cache ou outro estado local. Como `lobby.py`/`in_game.py`/`painel.py` rodam como script, o código novo já vale na próxima vez que clicar em **Start**, sem rebuildar nem gerar instalador de novo.

`start.py`/`updater.py` também são sincronizados no disco por completude, mas como `start.exe` é compilado, mudança neles só tem efeito depois de um `python build.py` + novo instalador manual — é o único caso que ainda exige isso.
