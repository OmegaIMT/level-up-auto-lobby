# Auto Lobby Level Up — Bot Dota 2

Automação em Python para farmar ciclos de partida (Re-Host) no Dota 2: abre o jogo, digita a senha, entra na lobby certa, aguarda a partida, coleta bônus/tesouros/evento durante o jogo e reinicia o ciclo sozinho.

## Arquitetura

O bot é dividido em processos independentes, cada um lançado pelo anterior:

| Arquivo | Papel |
|---|---|
| `start.py` | GUI (Tkinter) de configuração. Salva `config.json`, checa update no GitHub e lança `lobby.py`/`painel.py`. |
| `lobby.py` | Abre o Dota, digita senha, busca a sala pelo prefixo `up-`, entra na partida e lança `in_game.py`. |
| `in_game.py` | Roda durante a partida: desativa XP, coleta bônus/tesouro, organiza mochila, dispara o evento, detecta fim de partida e reinicia o ciclo (`lobby.py`) até bater o `rehost_max`. |
| `painel.py` | Overlay transparente e click-through no canto da tela mostrando `partidas/rehost` e `ciclos`. |
| `updater.py` | Auto-update via GitHub Releases (baixa `.exe` novos e `language.zip`). |
| `coord.py` | Ferramenta manual (rodar à parte) para capturar coordenadas fixas de clique e gerar `coords_base.json`. |
| `build.py` + `build.spec` | Empacota os 4 entrypoints em `.exe` via PyInstaller e organiza a pasta `dist/`. |

Toda a automação de tela funciona por **reconhecimento de imagem** (`pyautogui.locateOnScreen`), não por memory-reading nem OCR. As imagens de referência ficam em:

```
language/<idioma>/<resolução>/lobby/    # telas de menu e senha (dependem de idioma)
language/<idioma>/<resolução>/in_game/  # bonus/contagem (dependem de idioma)
language/global/<resolução>/suporte/    # itens, tesouro (independem de idioma)
language/global/<resolução>/event/      # evento
language/global/<resolução>/error/      # telas de erro/desconexão
```

Idiomas disponíveis: `pt-br`, `en-us`, `ru`, `zh-cn`. Resoluções calibradas: `1920x1080` e `1600x900`.

Coordenadas de clique fixo (mochila, status, gold) ficam em `coords_base.json` e são escaladas em runtime pra resolução configurada.

## Pré-requisitos

* Windows + Python 3.10 ou superior, com **"Add Python to PATH"** marcado na instalação.
* Dota 2 instalado (via Steam).

## Instalação

```bash
setup.bat
```

Isso atualiza o `pip` e instala tudo do `requirements.txt` (`pyautogui`, `keyboard`, `opencv-python` — este último é exigido pelo `pyautogui` para o parâmetro `confidence` de matching por template).

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

Roda o PyInstaller com `build.spec` e organiza `level-up.ico` e `language/` na raiz de `dist/Dota-level-up-lobby/`.

## Release / auto-update

O `updater.py` consulta a última *Release* do repositório no GitHub. Pra publicar uma atualização:

1. Buildar (`python build.py`).
2. Criar uma Release no GitHub com tag `vX.Y.Z`.
3. Anexar os `.exe` que mudaram (`start.exe`, `lobby.exe`, `in_game.exe`, `painel.exe`) e, se as imagens mudaram, um `language.zip` (zipando a pasta `language/` inteira).

No próximo boot, `start.py` detecta a versão nova e atualiza sozinho (o próprio `start.exe` troca via um `.bat` temporário depois que o processo atual encerra).
