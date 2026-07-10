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

a_start   = _analysis('start.py')
a_in_game = _analysis('in_game.py')
a_lobby   = _analysis('lobby.py')
a_painel  = _analysis('painel.py')

pyz_start   = PYZ(a_start.pure)
pyz_in_game = PYZ(a_in_game.pure)
pyz_lobby   = PYZ(a_lobby.pure)
pyz_painel  = PYZ(a_painel.pure)

exe_start   = _exe(pyz_start,   a_start,   'start')
exe_in_game = _exe(pyz_in_game, a_in_game, 'in_game')
exe_lobby   = _exe(pyz_lobby,   a_lobby,   'lobby')
exe_painel  = _exe(pyz_painel,  a_painel,  'painel')

coll = COLLECT(
    exe_start,   a_start.binaries,   a_start.datas,
    exe_in_game, a_in_game.binaries, a_in_game.datas,
    exe_lobby,   a_lobby.binaries,   a_lobby.datas,
    exe_painel,  a_painel.binaries,  a_painel.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Dota-level-up-lobby',
)
