# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['dutch_tender_scraper.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'feedparser',
        'dateutil',
        'dateutil.parser',
        'openpyxl.cell._writer',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'PIL',
        'numpy',
        'pandas',
        'matplotlib',
        'anthropic',
        'playwright',
        'selenium',
        'pytest',
        'IPython',
        'jupyter',
        'notebook',
    ],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DutchTenderScraper',
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
)
