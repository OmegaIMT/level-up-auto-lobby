"""
build.py — Compila o projeto e copia language/ e level-up.ico para a raiz do dist.

Uso:
    python build.py

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


if __name__ == "__main__":
    print("==> Compilando com PyInstaller...")
    run_pyinstaller()

    print("==> Copiando arquivos para a raiz do dist...")
    copy_to_root()

    print(f"\n Build concluído: dist/{DIST_NAME}/")