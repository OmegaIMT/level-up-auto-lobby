"""
build.py — Compila start.exe e copia pro dist tudo que ele precisa achar do
lado (source dos outros processos + dados), já que só start.exe é .exe.

Uso:
    python build.py

lobby.py/in_game.py/painel.py rodam como script (não .exe) pra permitirem
update via git sem rebuild (ver updater.py). Por isso precisam estar na
raiz do dist junto do start.exe, não só empacotados dentro dele.
"""
import os
import sys
import shutil
import subprocess

DIST_NAME = "Dota-level-up-lobby"
DIST_ROOT = os.path.join("dist", DIST_NAME)

# Mesma lista que updater.py sincroniza via git — mantém dist e update
# consistentes.
SOURCE_FILES = [
    "lobby.py",
    "in_game.py",
    "painel.py",
    "updater.py",
    "coords_base.json",
    "requirements.txt",
    "level-up.ico",
    "version.txt",
]
SOURCE_DIRS = ["language"]


def run_pyinstaller() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "build.spec", "--noconfirm"],
        check=True,
    )
    if result.returncode != 0:
        sys.exit(result.returncode)


def copy_to_root() -> None:
    for fname in SOURCE_FILES:
        if not os.path.exists(fname):
            continue
        dst = os.path.join(DIST_ROOT, fname)
        shutil.copy2(fname, dst)
        print(f"[OK] {dst}")

    for dname in SOURCE_DIRS:
        if not os.path.exists(dname):
            continue
        dst = os.path.join(DIST_ROOT, dname)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(dname, dst)
        print(f"[OK] {dst}")


if __name__ == "__main__":
    print("==> Compilando com PyInstaller...")
    run_pyinstaller()

    print("==> Copiando source/dados para a raiz do dist...")
    copy_to_root()

    print(f"\n Build concluído: dist/{DIST_NAME}/")