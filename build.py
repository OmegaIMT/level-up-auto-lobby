"""
build.py — Compila o projeto (todos os .exe), copia os arquivos de dados
pra raiz do dist e gera o zip pronto pra subir como asset de Release.

Uso:
    1. Edita version.json (sobe o "version").
    2. python build.py
    3. Cria uma Release no GitHub com a tag da versão e sobe
       dist/Dota-level-up-lobby.zip como asset.
    4. Faz commit/push do version.json na main — é isso que o updater
       compara pra saber se tem versão nova.

O PyInstaller por design joga arquivos DATA dentro de _internal/.
Este script roda o build e depois move os arquivos para o lugar certo
na raiz de dist/Dota-level-up-lobby/, onde os .exe esperam encontrá-los.
"""
import os
import sys
import shutil
import subprocess

DIST_NAME = "Dota-level-up-lobby"
DIST_ROOT = os.path.join("dist", DIST_NAME)
ZIP_PATH = os.path.join("dist", DIST_NAME)  # shutil.make_archive adiciona o .zip

# Dados que o exe lê em runtime e o PyInstaller não empacota sozinho
# (não são import, então não entram na Analysis automaticamente).
DATA_FILES = [
    "coords_base.json",
    "version.json",
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


if __name__ == "__main__":
    print("==> Compilando com PyInstaller...")
    run_pyinstaller()

    print("==> Copiando arquivos para a raiz do dist...")
    copy_to_root()

    print("==> Gerando zip pra subir na Release...")
    zip_path = zip_dist()

    print(f"\n Build concluído: dist/{DIST_NAME}/")
    print(f" Sobe este arquivo como asset da Release: {zip_path}")
