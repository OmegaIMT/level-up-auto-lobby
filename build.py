"""
build.py — Compila o projeto (todos os .exe), copia os dados, gera o zip
pra Release e já compila o instalador (Setup.exe) via Inno Setup.

Uso:
    1. Edita version.json (sobe o "version").
    2. python build.py
    3. Cria uma Release no GitHub com a tag da versão, sobe
       dist/Dota-level-up-lobby.zip como asset (é o que o updater baixa)
       e o Setup.exe de installer_output/ se quiser distribuir separado.
    4. Faz commit/push — version.json é o que o updater compara pra saber
       se tem versão nova.

O PyInstaller por design joga arquivos DATA dentro de _internal/.
Este script roda o build e depois move os arquivos para o lugar certo
na raiz de dist/Dota-level-up-lobby/, onde os .exe esperam encontrá-los.
"""
import json
import os
import shutil
import subprocess
import sys

DIST_NAME = "Dota-level-up-lobby"
DIST_ROOT = os.path.join("dist", DIST_NAME)
ZIP_PATH = os.path.join("dist", DIST_NAME)  # shutil.make_archive adiciona o .zip
INSTALLER_SCRIPT = "installer.iss"

# Dados que o exe lê em runtime e o PyInstaller não empacota sozinho
# (não são import, então não entram na Analysis automaticamente).
DATA_FILES = [
    "coords_base.json",
    "version.json",
]

# Onde o Inno Setup 6/7 costuma instalar o compilador, além do PATH.
ISCC_CANDIDATES = [
    r"C:\Program Files\Inno Setup 7\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
]


def run_pyinstaller() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "build.spec", "--noconfirm"],
        check=True,
    )
    if result.returncode != 0:
        sys.exit(result.returncode)


def copy_to_root() -> None:
    # 1. Ícone
    ico_src = "level-up.ico"
    ico_dst = os.path.join(DIST_ROOT, "level-up.ico")
    if os.path.exists(ico_src):
        shutil.copy2(ico_src, ico_dst)
        print(f"[OK] {ico_dst}")

    # 2. Pasta language/
    lang_src = "language"
    lang_dst = os.path.join(DIST_ROOT, "language")
    if os.path.exists(lang_src):
        if os.path.exists(lang_dst):
            shutil.rmtree(lang_dst)
        shutil.copytree(lang_src, lang_dst)
        print(f"[OK] {lang_dst}")

    # 3. Arquivos de dados (coords_base.json, version.json)
    for fname in DATA_FILES:
        if os.path.exists(fname):
            shutil.copy2(fname, os.path.join(DIST_ROOT, fname))
            print(f"[OK] {os.path.join(DIST_ROOT, fname)}")


def zip_dist() -> str:
    archive = shutil.make_archive(ZIP_PATH, "zip", root_dir=DIST_ROOT)
    print(f"[OK] {archive}")
    return archive


def read_version() -> str:
    with open("version.json", "r", encoding="utf-8") as f:
        return json.load(f)["version"]


def find_iscc() -> str | None:
    found = shutil.which("ISCC") or shutil.which("ISCC.exe")
    if found:
        return found
    return next((c for c in ISCC_CANDIDATES if os.path.exists(c)), None)


def build_installer(version: str) -> str | None:
    if not os.path.exists(INSTALLER_SCRIPT):
        print(f"[SKIP] {INSTALLER_SCRIPT} não existe, pulando instalador.")
        return None

    iscc = find_iscc()
    if not iscc:
        print("[SKIP] Inno Setup (ISCC.exe) não encontrado — instalador não gerado. "
              "Instala em https://jrsoftware.org/isdl.php pra habilitar essa etapa.")
        return None

    subprocess.run(
        [iscc, f"/DMyAppVersion={version}", INSTALLER_SCRIPT],
        check=True,
    )
    setup_path = os.path.join("installer_output", f"Dota-Level-Up-Lobby-Setup-{version}.exe")
    print(f"[OK] {setup_path}")
    return setup_path


if __name__ == "__main__":
    version = read_version()
    print(f"==> Versão: {version}")

    print("==> Compilando com PyInstaller...")
    run_pyinstaller()

    print("==> Copiando arquivos para a raiz do dist...")
    copy_to_root()

    print("==> Gerando zip pra subir na Release...")
    zip_path = zip_dist()

    print("==> Gerando instalador...")
    setup_path = build_installer(version)

    print(f"\n Build concluído: dist/{DIST_NAME}/")
    print(f" Asset da Release (auto-update): {zip_path}")
    if setup_path:
        print(f" Instalador (distribuição manual): {setup_path}")
