"""
updater.py
Auto-update via GitHub Releases — não via raw.githubusercontent.com arquivo a arquivo.

Por quê Releases:
O build.py gera .exe via PyInstaller. Não faz sentido versionar binário solto
numa branch normal. O fluxo certo é: você builda, sobe uma Release no GitHub
(https://github.com/OmegaIMT/level-up-auto-lobby/releases/new) com os .exe
(e opcionalmente um language.zip) como assets, e o updater baixa daquela release.

CONVENÇÃO DA RELEASE
---------------------
- tag_name da release = versão. Ex: "v1.0.1" (o "v" é opcional, ignorado na comparação).
- Assets esperados — todos opcionais, só atualiza o que existir na release:
    start.exe, lobby.exe, in_game.exe, painel.exe   -> substituem o exe correspondente
    language.zip                                     -> extraído na raiz do projeto,
                                                          sobrescrevendo language/
  (zipar a pasta "language" inteira, não só o conteúdo dela, pra extrair certo
  na raiz: language.zip -> ./language/...)

COMO USAR (já integrado no start.py)
-------------------------------------
    import updater
    updater.confirm_pending_version_if_any()
    resultado = updater.check_for_updates()
    if resultado.self_update_ready:
        updater.apply_self_update_and_restart(resultado.self_update_path)
        os._exit(0)

PRIMEIRA EXECUÇÃO
------------------
Se não existir version.txt na pasta, a versão local é tratada como "0.0.0",
então a primeira release publicada sempre vai disparar update. Se quiser
"pular" a primeira, crie um version.txt manualmente no dist com a versão
correspondente à build atual.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional

GITHUB_OWNER = "OmegaIMT"
GITHUB_REPO  = "level-up-auto-lobby"
GITHUB_API_LATEST_RELEASE = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

# Se o repositório virar privado no futuro, defina um token com escopo de
# leitura aqui (ou via variável de ambiente GITHUB_UPDATE_TOKEN).
GITHUB_TOKEN = os.environ.get("GITHUB_UPDATE_TOKEN", "")

VERSION_FILE = "version.txt"
REQUEST_TIMEOUT = 10  # segundos; rede ruim/off falha rápido e silencioso

# Nome do exe que representa "o processo atual" — não pode se auto-sobrescrever
# enquanto roda no Windows (arquivo fica travado).
SELF_EXE_NAME = "start.exe"

# Assets simples: nome do asset na release == nome do arquivo local a substituir.
EXE_ASSETS = ["start.exe", "lobby.exe", "in_game.exe", "painel.exe"]
LANGUAGE_ZIP_ASSET = "language.zip"


@dataclass
class UpdateResult:
    checked: bool = False              # se conseguiu falar com a API do GitHub
    updated: bool = False              # se algo (que não o próprio exe) foi atualizado
    remote_version: Optional[str] = None
    local_version: Optional[str] = None
    self_update_ready: bool = False    # True se start.exe.new foi baixado e precisa reiniciar
    self_update_path: Optional[str] = None
    updated_files: List[str] = field(default_factory=list)
    error: Optional[str] = None


def _parse_version(v: str) -> tuple:
    """'v1.3.0' ou '1.3.0' -> (1, 3, 0). Ignora sufixos não numéricos com segurança."""
    v = v.strip()
    if v.lower().startswith("v"):
        v = v[1:]
    parts = []
    for chunk in v.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts) if parts else (0,)


def _version_is_newer(remote: str, local: str) -> bool:
    return _parse_version(remote) > _parse_version(local)


def get_local_version() -> str:
    if not os.path.exists(VERSION_FILE):
        return "0.0.0"
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or "0.0.0"
    except Exception:
        return "0.0.0"


def _save_local_version(version: str) -> None:
    try:
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            f.write(version.strip())
    except Exception:
        pass


def _request(url: str, accept: str = "application/vnd.github+json") -> Optional[bytes]:
    headers = {"User-Agent": "level-up-auto-lobby-updater", "Accept": accept}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, Exception):
        return None


def get_latest_release() -> Optional[dict]:
    raw = _request(GITHUB_API_LATEST_RELEASE)
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, dict) and "tag_name" in data:
            return data
    except Exception:
        pass
    return None


def _download_asset(asset: dict) -> Optional[bytes]:
    url = asset.get("browser_download_url")
    if not url:
        return None
    return _request(url, accept="application/octet-stream")


def _is_self(filename: str) -> bool:
    return filename.lower() == SELF_EXE_NAME.lower()


def check_for_updates() -> UpdateResult:
    """
    Verifica a última Release no GitHub e aplica o que houver de novo.
    Chamar no início do start.py, antes de montar a UI. Falha de rede é
    sempre silenciosa (não trava o app).
    """
    result = UpdateResult()

    release = get_latest_release()
    if release is None:
        result.error = "sem conexão com o GitHub ou nenhuma release publicada"
        return result

    result.checked = True
    remote_version = str(release.get("tag_name", "0.0.0"))
    local_version = get_local_version()
    result.remote_version = remote_version
    result.local_version = local_version

    if not _version_is_newer(remote_version, local_version):
        return result  # já está na versão mais recente

    assets: List[dict] = release.get("assets", []) or []
    assets_by_name: Dict[str, dict] = {a.get("name", ""): a for a in assets}

    all_ok = True

    # 1. Executáveis — substituição direta 1 pra 1
    for exe_name in EXE_ASSETS:
        asset = assets_by_name.get(exe_name)
        if asset is None:
            continue  # release não trouxe esse exe, ignora

        raw = _download_asset(asset)
        if raw is None:
            all_ok = False
            continue

        try:
            fd, tmp_path = tempfile.mkstemp(prefix="update_", suffix=".tmp")
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
        except Exception:
            all_ok = False
            continue

        if _is_self(exe_name):
            # Não sobrescreve o próprio exe em execução. Fica pronto como .new
            # pra troca ser feita depois que o processo atual encerrar.
            self_new_path = exe_name + ".new"
            try:
                os.replace(tmp_path, self_new_path)
                result.self_update_ready = True
                result.self_update_path = self_new_path
            except Exception:
                all_ok = False
            continue

        try:
            os.replace(tmp_path, exe_name)
            result.updated_files.append(exe_name)
        except Exception:
            all_ok = False

    # 2. language.zip (opcional) — extrai na raiz, sobrescrevendo language/
    lang_asset = assets_by_name.get(LANGUAGE_ZIP_ASSET)
    if lang_asset is not None:
        raw = _download_asset(lang_asset)
        if raw is None:
            all_ok = False
        else:
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    zf.extractall(".")
                result.updated_files.append(LANGUAGE_ZIP_ASSET)
            except Exception:
                all_ok = False

    result.updated = len(result.updated_files) > 0

    # Só grava a versão nova localmente se tudo que não era o próprio exe deu
    # certo. Se o self-update está pendente, a confirmação fica pra depois do
    # restart (ver confirm_pending_version_if_any), pra não perder o update
    # caso o restart falhe no meio do caminho.
    if all_ok and not result.self_update_ready:
        _save_local_version(remote_version)
    elif all_ok and result.self_update_ready:
        try:
            with open(VERSION_FILE + ".pending", "w", encoding="utf-8") as f:
                f.write(remote_version)
        except Exception:
            pass

    return result


def confirm_pending_version_if_any() -> None:
    """Chamar logo no início do start.py, antes de check_for_updates().
    Se um self-update foi concluído no boot anterior, confirma a versão."""
    pending_file = VERSION_FILE + ".pending"
    if os.path.exists(pending_file):
        try:
            with open(pending_file, "r", encoding="utf-8") as f:
                pending_version = f.read().strip()
            if pending_version:
                _save_local_version(pending_version)
            os.remove(pending_file)
        except Exception:
            pass


def apply_self_update_and_restart(self_update_path: str) -> None:
    """
    Troca o exe atual (SELF_EXE_NAME) pelo self_update_path e reabre o processo.
    Chamar e, em seguida, encerrar o processo atual (sys.exit/os._exit) pra
    liberar o arquivo antigo pro .bat conseguir apagá-lo.
    """
    if sys.platform != "win32":
        try:
            os.replace(self_update_path, SELF_EXE_NAME)
            subprocess.Popen([os.path.abspath(SELF_EXE_NAME)])
        except Exception:
            pass
        return

    bat_path = os.path.join(tempfile.gettempdir(), "apply_update.bat")
    exe_abspath = os.path.abspath(SELF_EXE_NAME)
    new_abspath = os.path.abspath(self_update_path)

    bat_content = f"""@echo off
:wait_loop
tasklist /FI "IMAGENAME eq {SELF_EXE_NAME}" | find /I "{SELF_EXE_NAME}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_loop
)
move /Y "{new_abspath}" "{exe_abspath}" >nul
start "" "{exe_abspath}"
del "%~f0"
"""
    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass