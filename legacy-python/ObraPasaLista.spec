# -*- mode: python ; coding: utf-8 -*-
#
# Build reproducible del ejecutable ObraPasaLista.
# Se invoca con:  pyinstaller --noconfirm --clean ObraPasaLista.spec
# (ver build_obrapasalista.bat, que hace esto automaticamente).
#
import os
from PyInstaller.utils.hooks import collect_all

# SPECPATH lo define PyInstaller automaticamente: carpeta donde vive este .spec
SRC_DIR = os.path.join(SPECPATH, 'src')
APP_MAIN = os.path.join(SRC_DIR, 'app.py')

datas = []
binaries = []
hiddenimports = []

# Empaquetado robusto del stack de Flask: --collect-all evita errores de
# "ModuleNotFoundError" en la maquina final, donde el usuario no puede
# instalar nada por su cuenta si algo falta.
for _pkg in ('flask', 'jinja2', 'werkzeug', 'click', 'itsdangerous', 'blinker', 'markupsafe'):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

# Bootstrap vendorizado (CSS/JS/iconos servidos por Flask como estaticos).
# No esta en el repo de git (revisar), asi que solo se incluye si existe
# localmente en la maquina donde se compila.
static_dir = os.path.join(SRC_DIR, 'static')
if os.path.isdir(static_dir):
    datas.append((static_dir, 'static'))

a = Analysis(
    [APP_MAIN],
    pathex=[SRC_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ObraPasaLista',
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
