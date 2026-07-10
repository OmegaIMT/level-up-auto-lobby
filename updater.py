"""
updater.py
Auto-update via asset de Release do GitHub — baixa o build (.exe) pronto,
não o código-fonte.

COMO FUNCIONA
-------------
- version.json na raiz do repo (branch main) é a fonte da verdade da versão
  ({"version": "2.2.1"}).
- start.exe checa esse arquivo via raw.githubusercontent.com toda vez que
  abre.
- Se a versão remota for maior que o version.json local, busca a Release
  mais recente (GitHub Releases API), acha o asset .zip anexado nela e
  baixa ele — esse zip é o dist/Dota-level-up-lobby/ inteiro, com todos os
  .exe já compilados (ver build.py).
- Extrai e sobrescreve tudo (exceto config.json/status.json/cache — estado
  local, nunca vem no pacote de build).
- start.exe é o processo rodando durante o check, então não dá pra
  sobrescrever o arquivo dele em uso — troca por rename (start.exe vira
  start.exe.old) e o novo já assume o nome; o .old é removido no próximo
  start (ver start.py:_cleanup_old_exe).

CONVENÇÃO PRA PUBLICAR UMA ATUALIZAÇÃO
---------------------------------------
1. Edita version.json (sobe o "version").
2. `python build.py` — compila tudo e gera dist/Dota-level-up-lobby.zip.
3. Cria uma Release no GitHub (tag = versão) e sobe esse .zip como asset.
4. `git push` do version.json pra main. Pronto — quem abrir o app pega a
   versão nova.

PRIMEIRA EXECUÇÃO
------------------
Se não existir version.json local, a versão é tratada como "0.0.0", então a
primeira checagem sempre baixa a versão atual do repo.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import time
import urllib.request
import urllib.error
import zipfile
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# stage: "checking" | "found" | "downloading" | "updated" | "up_to_date" | "error"
# percent: 0-100 durante "downloading" (None se o servidor não mandar
# Content-Length — raro em asset de Release, mas tratado mesmo assim).
ProgressCallback = Callable[[str, Optional[int]], None]


def _notify(cb: Optional[ProgressCallback], stage: str, percent: Optional[int] = None) -> None:
    if cb is not None:
        try:
            cb(stage, percent)
        except Exception:
            pass


def _fail(result: "UpdateResult", cb: Optional[ProgressCallback], message: str) -> "UpdateResult":
    result.error = message
    _notify(cb, "error")
    return result

GITHUB_OWNER = "OmegaIMT"
GITHUB_REPO = "level-up-auto-lobby"
GITHUB_BRANCH = "main"

RAW_VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/version.json"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

# Se o repositório virar privado no futuro, defina um token com escopo de
# leitura aqui (ou via variável de ambiente GITHUB_UPDATE_TOKEN).
GITHUB_TOKEN = os.environ.get("GITHUB_UPDATE_TOKEN", "")

VERSION_FILE = "version.json"
REQUEST_TIMEOUT = 15  # segundos; rede ruim/off falha rápido e silencioso

# Nunca sobrescreve estes — são estado local, não fazem parte do pacote
# de build (build.py não gera nenhum deles).
PROTECTED_PATHS = {"config.json", "status.json", "version.json"}


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
            data = json.load(f)
            return str(data.get("version", "0.0.0")).strip() or "0.0.0"
    except Exception:
        return "0.0.0"


def _save_local_version(version: str) -> None:
    try:
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            json.dump({"version": version.strip()}, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


def _request(
    url: str,
    accept: str = "application/vnd.github+json",
    progress_cb: Optional[ProgressCallback] = None,
) -> Optional[bytes]:
    headers = {"User-Agent": "level-up-auto-lobby-updater", "Accept": accept}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            if progress_cb is None:
                return resp.read()

            total_header = resp.headers.get("Content-Length")
            total = int(total_header) if total_header else None
            chunks = []
            read = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                read += len(chunk)
                _notify(progress_cb, "downloading", int(read * 100 / total) if total else None)
            return b"".join(chunks)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, Exception):
        return None


def _get_remote_version() -> Optional[str]:
    raw = _request(RAW_VERSION_URL, accept="application/vnd.github.raw")
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8", errors="ignore"))
        version = str(data.get("version", "")).strip()
        return version or None
    except Exception:
        return None


def _get_latest_release_zip_url() -> Optional[str]:
    """Acha o asset .zip anexado na Release mais recente."""
    raw = _request(LATEST_RELEASE_URL)
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8", errors="ignore"))
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.lower().endswith(".zip"):
                return asset.get("browser_download_url")
    except Exception:
        return None
    return None


def _apply_update(extracted_root: str) -> List[str]:
    """Copia tudo de extracted_root pra raiz do projeto, exceto
    PROTECTED_PATHS (estado local). Retorna o que foi de fato atualizado.
    start.exe é tratado à parte por _apply_update pra lidar com o arquivo
    em uso (ver replace_running_exe)."""
    updated: List[str] = []

    for entry in os.listdir(extracted_root):
        if entry in PROTECTED_PATHS:
            continue
        src = os.path.join(extracted_root, entry)
        dst = entry

        if entry == "start.exe":
            if not _replace_running_exe(src, dst):
                continue
            updated.append(entry)
            continue

        try:
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            updated.append(entry)
        except Exception:
            pass

    return updated


def _replace_running_exe(src: str, dst: str) -> bool:
    """start.exe é o processo rodando o updater — não dá pra sobrescrever
    o arquivo em uso direto (Windows tranca a imagem). Renomeia o atual
    pra .old (rename funciona em exe rodando) e coloca o novo no lugar;
    o .old é limpo no próximo start (start.py:_cleanup_old_exe)."""
    if not os.path.exists(dst):
        try:
            shutil.copy2(src, dst)
            return True
        except Exception:
            return False

    old_path = dst + ".old"
    try:
        if os.path.exists(old_path):
            os.remove(old_path)
        os.rename(dst, old_path)
        shutil.copy2(src, dst)
        return True
    except Exception:
        return False


def check_for_updates(progress_cb: Optional[ProgressCallback] = None) -> UpdateResult:
    """
    Compara version.json local com o do repo (main). Se tiver versão nova,
    baixa o asset .zip da Release mais recente (build já compilado) e
    sobrescreve tudo, sem mexer em estado local (config, status, cache).

    Chamar no início do start.py, antes de montar a UI. Falha de rede é
    sempre silenciosa (não trava o app).

    progress_cb(stage, percent), se passado, é chamado nos estágios:
    "checking" -> "up_to_date"/"error" (para) ou "found" -> "downloading"
    (com percent) -> "updated"/"error".
    """
    result = UpdateResult()

    _notify(progress_cb, "checking")
    remote_version = _get_remote_version()
    if remote_version is None:
        return _fail(result, progress_cb, "sem conexão com o GitHub ou version.json ausente no repo")

    result.checked = True
    local_version = get_local_version()
    result.remote_version = remote_version
    result.local_version = local_version

    if not _version_is_newer(remote_version, local_version):
        _notify(progress_cb, "up_to_date")
        return result  # já está na versão mais recente

    _notify(progress_cb, "found")

    zip_url = _get_latest_release_zip_url()
    if zip_url is None:
        return _fail(result, progress_cb, "nenhum asset .zip encontrado na Release mais recente")

    zip_bytes = _request(zip_url, accept="application/octet-stream", progress_cb=progress_cb)
    if zip_bytes is None:
        return _fail(result, progress_cb, "falha ao baixar atualização")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                zf.extractall(tmp_dir)
            result.updated_files = _apply_update(tmp_dir)
    except Exception as e:
        return _fail(result, progress_cb, f"falha ao aplicar atualização: {e}")

    result.updated = len(result.updated_files) > 0
    if result.updated:
        _save_local_version(remote_version)
        _notify(progress_cb, "updated")

    return result
