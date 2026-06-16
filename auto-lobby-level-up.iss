# -*- mode: python ; coding: utf-8 -*-
import os
import shutil

# 1. Configuração do 'start'
a_start = Analysis(
    ['start.py'],
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
pyz_start = PYZ(a_start.pure)
exe_start = EXE(
    pyz_start,
    a_start.scripts,
    [],
    exclude_binaries=True,
    name='start',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['level-up.ico'],
)

# 2. Configuração do 'in_game'
a_in_game = Analysis(
    ['in_game.py'],
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
pyz_in_game = PYZ(a_in_game.pure)
exe_in_game = EXE(
    pyz_in_game,
    a_in_game.scripts,
    [],
    exclude_binaries=True,
    name='in_game',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['level-up.ico'],
)

# 3. Configuração do 'lobby'
a_lobby = Analysis(
    ['lobby.py'],
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
pyz_lobby = PYZ(a_lobby.pure)
exe_lobby = EXE(
    pyz_lobby,
    a_lobby.scripts,
    [],
    exclude_binaries=True,
    name='lobby',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['level-up.ico'],
)

# 4. Configuração do 'painel'
a_painel = Analysis(
    ['painel.py'],
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
pyz_painel = PYZ(a_painel.pure)
exe_painel = EXE(
    pyz_painel,
    a_painel.scripts,
    [],
    exclude_binaries=True,
    name='painel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['level-up.ico'],
)

# ==========================================
# Agrupamento de tudo em uma única pasta
# ==========================================
coll = COLLECT(
    exe_start,
    a_start.binaries,
    a_start.datas, 
    
    exe_in_game,
    a_in_game.binaries,
    a_in_game.datas,
    
    exe_lobby,
    a_lobby.binaries,
    a_lobby.datas,
    
    exe_painel,
    a_painel.binaries,
    a_painel.datas,
    
    # Deixamos o PyInstaller gerar aqui primeiro (ele vai jogar pro _internal por padrão)
    Tree('language', prefix='language'),
    [('level-up.ico', 'level-up.ico', 'DATA')],

    strip=False,
    upx=True,
    upx_exclude=[],
    name='Dota-level-up-lobby',  
)

# ==========================================
# SCRIPT PÓS-BUILD: FORÇAR SAÍDA DO _INTERNAL
# ==========================================
dist_root = os.path.join('dist', 'Dota-level-up-lobby')
internal_dir = os.path.join(dist_root, '_internal')

if os.path.exists(internal_dir):
    print("--- Corrigindo estrutura de pastas (Bastos Develop) ---")
    
    # 1. Movendo a pasta 'language' para a raiz
    lang_internal = os.path.join(internal_dir, 'language')
    lang_target = os.path.join(dist_root, 'language')
    if os.path.exists(lang_internal) and not os.path.exists(lang_target):
        shutil.move(lang_internal, lang_target)
        print("[OK] Pasta 'language' movida para a raiz.")

    # 2. Movendo o arquivo 'level-up.ico' para a raiz
    ico_internal = os.path.join(internal_dir, 'level-up.ico')
    ico_target = os.path.join(dist_root, 'level-up.ico')
    if os.path.exists(ico_internal) and not os.path.exists(ico_target):
        shutil.move(ico_internal, ico_target)
        print("[OK] Arquivo 'level-up.ico' movido para a raiz.")