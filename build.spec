# -*- mode: python ; coding: utf-8 -*-

def _analysis(script):
    return Analysis(
        [script],
        pathex=[],
        binaries=[],
        datas=[],
        hiddenimports=[],
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=[],
        noarchive=False,
        optimize=0,
    )

def _exe(pyz, a, name):
    return EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=['level-up.ico'],
    )

# lobby.py/in_game.py/painel.py NÃO são mais empacotados em .exe — rodam
# como script direto (python lobby.py), lançados pelo start.exe. Assim o
# updater consegue atualizar o código deles via git sem rebuild. Ver
# updater.py e start.py (_find_python_cmd/PYTHON_CMD).
a_start = _analysis('start.py')

pyz_start = PYZ(a_start.pure)

exe_start = _exe(pyz_start, a_start, 'start')

coll = COLLECT(
    exe_start, a_start.binaries, a_start.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Dota-level-up-lobby',
)
