# ck-pdf-unlocker.spec
# Build with:  pyinstaller ck-pdf-unlocker.spec
# Output:      dist/ck-pdf-unlocker/  (one-folder mode)

from PyInstaller.utils.hooks import collect_submodules
import sys

block_cipher = None

a = Analysis(
    ['ck-pdf-unlocker.pyw'],
    pathex=[],
    binaries=[],
    datas=[
        ('updater.py',                    '.'),
        ('telemetry.py',                  '.'),
        ('ck-pdf-unlocker.ico',           '.'),
        ('ck-pdf-unlocker-1024.png',      '.'),
    ],
    hiddenimports=[
        'updater',
        'telemetry',
        'pikepdf',
        'pikepdf._core',
        'packaging',
        'packaging.version',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        *collect_submodules('pikepdf'),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# One-folder mode: EXE contains only the bootloader + scripts.
# All binaries, data files, and zipped modules go into COLLECT.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ck-pdf-unlocker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no console window (windowed app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='ck-pdf-unlocker.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ck-pdf-unlocker',
)
