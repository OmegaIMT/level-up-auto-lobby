# -*- mode: python ; coding: utf-8 -*-

def _analysis(script, hiddenimports=None):
    return Analysis(
        [script],
        pathex=[],
        binaries=[],
        datas=[],
        hiddenimports=hiddenimports or [],
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

# cv2 (opencv-python): pyautogui/pyscreeze só importa por dentro, condicionado
# a locateOnScreen(confidence=...) - PyInstaller às vezes não pega essa
# dependência sozinho, e sem cv2 empacotado TODA busca de imagem com
# confidence falha com exceção (antes mascarada como "imagem não achada" -
# ver fix em in_game.py/fim_game.py _locate_raw). Forçando aqui pra nunca
# mais sumir de um build silenciosamente.
_CV2 = ['cv2']

# DLL de vídeo do opencv (decoder ffmpeg) - vem de brinde no pacote, o bot
# NUNCA usa (só faz matchTemplate em screenshot estático, não vídeo). É o
# alvo clássico de falso-positivo de antivírus (Defender adora colocar
# opencv_videoio_ffmpeg*.dll em quarentena) - tirando do build elimina a DLL
# problemática sem tirar o cv2 de verdade (mantém a busca por confidence
# funcionando normal).
def _strip_ffmpeg_dll(binaries):
    return [b for b in binaries if 'ffmpeg' not in b[0].lower()]

a_start    = _analysis('start.py')
a_in_game  = _analysis('in_game.py', hiddenimports=_CV2)
a_fim_game = _analysis('fim_game.py', hiddenimports=_CV2)
a_lobby    = _analysis('lobby.py', hiddenimports=_CV2)
a_painel   = _analysis('painel.py')
a_resumo   = _analysis('resumo.py')

a_in_game.binaries  = _strip_ffmpeg_dll(a_in_game.binaries)
a_fim_game.binaries = _strip_ffmpeg_dll(a_fim_game.binaries)
a_lobby.binaries    = _strip_ffmpeg_dll(a_lobby.binaries)

pyz_start    = PYZ(a_start.pure)
pyz_in_game  = PYZ(a_in_game.pure)
pyz_fim_game = PYZ(a_fim_game.pure)
pyz_lobby    = PYZ(a_lobby.pure)
pyz_painel   = PYZ(a_painel.pure)
pyz_resumo   = PYZ(a_resumo.pure)

exe_start    = _exe(pyz_start,    a_start,    'start')
exe_in_game  = _exe(pyz_in_game,  a_in_game,  'in_game')
exe_fim_game = _exe(pyz_fim_game, a_fim_game, 'fim_game')
exe_lobby    = _exe(pyz_lobby,    a_lobby,    'lobby')
exe_painel   = _exe(pyz_painel,   a_painel,   'painel')
exe_resumo   = _exe(pyz_resumo,   a_resumo,   'resumo')

coll = COLLECT(
    exe_start,    a_start.binaries,    a_start.datas,
    exe_in_game,  a_in_game.binaries,  a_in_game.datas,
    exe_fim_game, a_fim_game.binaries, a_fim_game.datas,
    exe_lobby,    a_lobby.binaries,    a_lobby.datas,
    exe_painel,   a_painel.binaries,   a_painel.datas,
    exe_resumo,   a_resumo.binaries,   a_resumo.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Dota-level-up-lobby',
)
