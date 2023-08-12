# -*- mode: python ; coding: utf-8 -*-


block_cipher = None

import os
import pkgutil

dateutil_path = os.path.dirname(pkgutil.get_loader("dateutil").path)


a = Analysis(
    ['discord_hvz/main.py'],
    pathex=[],
    binaries=[],
    datas=[(dateutil_path, 'dateutil')],
    hiddenimports=[
        "discord_hvz.commands",
        "discord_hvz.buttons",
        "discord_hvz.chatbot",
        "discord_hvz.display",
        "discord_hvz.item_tracker"
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Discord-HvZ',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['images\\avatar_icon.ico'],
)
