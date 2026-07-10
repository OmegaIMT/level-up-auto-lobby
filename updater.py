"""
updater.py
Auto-update direto do git — sem builda exe nem subir Release a cada versão.

COMO FUNCIONA
-------------
- version.txt na raiz do repo (branch main) é a fonte da verdade da versão.
- start.exe (o único exe que existe hoje) checa esse arquivo via
  raw.githubusercontent.com toda vez que abre.
- Se a versão remota for maior que o version.txt local, baixa o repo inteiro
  (zipball da API do GitHub) e sobrescreve só os arquivos de SYNC_FILES/
  SYNC_DIRS — ou seja, lobby.py, in_game.py, painel.py, language/, etc.
- lobby.py/in_game.py/painel.py sempre rodam como script (python lobby.py),
  nunca como .exe, então pegam o código novo na hora, sem rebuild.
- start.py/updater.py também são sincronizados no disco por completude, mas
  como start.exe é compilado, mudanças neles só valem depois de um rebuild
  manual (python build.py) — é o único caso que ainda exige isso.

CONVENÇÃO
---------
- version.txt: só o número da versão em texto puro, ex "2.2.0".
- Pra publicar uma atualização: edita os .py/language/coords que quiser,
  sobe a versão em version.txt, `git push` pra main. Pronto.

PRIMEIRA EXECUÇÃO
------------------
Se não existir version.txt local, a versão é tratada como "0.0.0", então a
primeira checagem sempre baixa a versão atual do repo.
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import urllib.request
import urllib.error
import zipfile
from dataclasses import dataclass, field
from typing import List, Optional

GITHUB_OWNER = "OmegaIMT"
GITHUB_REPO = "level-up-auto-lobby"
GITHUB_BRANCH = "main"

RAW_VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/version.txt"
ZIPBALL_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/zipball/{GITHUB_BRANCH}"

# Se o repositório virar privado no futuro, defina um token com escopo de
# leitura aqui (ou via variável de ambiente GITHUB_UPDATE_TOKEN).
GITHUB_TOKEN = os.environ.get("GITHUB_UPDATE_TOKEN", "")

VERSION_FILE = "version.txt"
REQUEST_TIMEOUT = 15  # segundos; rede ruim/off falha rápido e silencioso

# Só esses arquivos/pastas são sobrescritos por um update — nunca mexe em
# config.json, status.json, cache_*, dist/, venv/ etc (estado local).
SYNC_FILES = [
    "lobby.py",
    "in_game.py",
    "painel.py",
    "start.py",
    "updater.py",
    "coord.py",
    "coords_base.json",
    "requirements.txt",
    "level-up.ico",
]
SYNC_DIRS = ["language"]


@dataclass
class UpdateResult:
    checked: bool = False              # se conseguiu falar com o GitHub
    updated: bool = False              # se algo foi atualizado
    remote_version: Optional[str] = None
    local_version: Optional[str] = None
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


def _get_remote_version() -> Optional[str]:
    raw = _request(RAW_VERSION_URL, accept="text/plain")
    if raw is None:
        return None
    version = raw.decode("utf-8", errors="ignore").strip()
    return version or None


def _apply_update(extracted_root: str) -> List[str]:
    """Copia SYNC_FILES/SYNC_DIRS de extracted_root pra raiz do projeto.
    Retorna a lista do que foi de fato atualizado."""
    updated: List[str] = []

    for fname in SYNC_FILES:
        src = os.path.join(extracted_root, fname)
        if os.path.isfile(src):
            shutil.copy2(src, fname)
            updated.append(fname)

    for dname in SYNC_DIRS:
        src_dir = os.path.join(extracted_root, dname)
        if os.path.isdir(src_dir):
            if os.path.exists(dname):
                shutil.rmtree(dname)
            shutil.copytree(src_dir, dname)
            updated.append(dname)

    return updated


def check_for_updates() -> UpdateResult:
    """
    Compara version.txt local com o do repo (main). Se tiver versão nova,
    baixa o repo inteiro (zipball) e sobrescreve os arquivos de código/dados
    (SYNC_FILES/SYNC_DIRS), sem mexer em estado local (config, cache, etc).

    Chamar no início do start.py, antes de montar a UI. Falha de rede é
    sempre silenciosa (não trava o app).
    """
    result = UpdateResult()

    remote_version = _get_remote_version()
    if remote_version is None:
        result.error = "sem conexão com o GitHub ou version.txt ausente no repo"
        return result

    result.checked = True
    local_version = get_local_version()
    result.remote_version = remote_version
    result.local_version = local_version

    if not _version_is_newer(remote_version, local_version):
        return result  # já está na versão mais recente

    # A API do GitHub responde 415 pro zipball se pedir accept
    # application/octet-stream (diferente do endpoint de asset de Release,
    # que aceita) — aqui precisa do accept default da API.
    zip_bytes = _request(ZIPBALL_URL)
    if zip_bytes is None:
        result.error = "falha ao baixar atualização"
        return result

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                zf.extractall(tmp_dir)

            entries = [e for e in os.listdir(tmp_dir) if os.path.isdir(os.path.join(tmp_dir, e))]
            if not entries:
                result.error = "zip de atualização vazio"
                return result

            extracted_root = os.path.join(tmp_dir, entries[0])
            result.updated_files = _apply_update(extracted_root)
    except Exception as e:
        result.error = f"falha ao aplicar atualização: {e}"
        return result

    result.updated = len(result.updated_files) > 0
    if result.updated:
        _save_local_version(remote_version)

    return result
