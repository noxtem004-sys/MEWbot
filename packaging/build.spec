# PyInstaller spec — build the Windows executable.
# Run FROM THE PROJECT ROOT on a Windows machine with the venv activated:
#     pyinstaller packaging/build.spec
#
# Output: dist/TelegramMeowBot/TelegramMeowBot.exe (portable folder build).
# For a single-file exe, add --onefile to the Analysis/EXE below, but a
# folder build starts faster and is easier to debug.

# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None
ROOT = Path.cwd()

a = Analysis(
    ['app.py'],
    pathex=[str(ROOT), str(ROOT / 'backend')],
    binaries=[],
    datas=[
        ('gui/styles/app.qss', 'gui/styles'),
        ('gui/resources/fonts', 'gui/resources/fonts'),
        ('gui/resources/icons', 'gui/resources/icons'),
    ],
    hiddenimports=[
        'aiogram', 'telethon', 'aiosqlite', 'qasync',
        'handlers.start', 'handlers.admin', 'keyboards.admin',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TelegramMeowBot',
    debug=False,
    strip=False,
    upx=False,
    console=False,          # no terminal window; the GUI has its own log panel
    icon='gui/resources/icons/app.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='TelegramMeowBot',
)
