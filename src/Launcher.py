#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ObraPasaLista — Launcher automático
Haz doble clic en start.bat (Windows) o ejecuta: python launcher.py
"""

import sys
import os
import subprocess
import time
import webbrowser
import venv
import platform
import threading
import socket

# ── CONFIG ────────────────────────────────────────────────────────────────────
PORT     = 5000
URL      = f'http://127.0.0.1:{PORT}'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(BASE_DIR, '.venv')
APP_FILE = os.path.join(BASE_DIR, 'app.py')
REQ_FILE = os.path.join(BASE_DIR, 'requirements.txt')
IS_WIN   = platform.system() == 'Windows'

PY  = os.path.join(VENV_DIR, 'Scripts' if IS_WIN else 'bin', 'python' + ('.exe' if IS_WIN else ''))
PIP = os.path.join(VENV_DIR, 'Scripts' if IS_WIN else 'bin', 'pip'    + ('.exe' if IS_WIN else ''))

# ── COLORES ANSI ──────────────────────────────────────────────────────────────
def _c(code, t): return f'\033[{code}m{t}\033[0m'
def ok(t):    print(_c('92',       f'  ✓  {t}'))
def info(t):  print(_c('96',       f'  →  {t}'))
def warn(t):  print(_c('93',       f'  ⚠  {t}'))
def err(t):   print(_c('91',       f'  ✗  {t}'))
def hdr(t):   print(_c('1;38;5;208', f'\n  {t}'))
def sep():    print(_c('90', '  ' + '─' * 44))

# ── HELPERS ───────────────────────────────────────────────────────────────────
def enable_ansi():
    """Activa colores ANSI en cmd/PowerShell de Windows."""
    if IS_WIN:
        os.system('')  # truco para activar modo VT100

def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def check_python():
    v = sys.version_info
    if v < (3, 8):
        err(f'Python 3.8+ requerido. Versión actual: {v.major}.{v.minor}')
        err('Descarga Python desde https://python.org')
        _pause_exit(1)
    ok(f'Python {v.major}.{v.minor}.{v.micro}')

def check_app():
    if not os.path.exists(APP_FILE):
        err(f'No se encuentra app.py en:')
        err(f'  {BASE_DIR}')
        err('Asegúrate de que launcher.py y app.py están en la misma carpeta.')
        _pause_exit(1)
    ok('app.py encontrado')

def create_venv():
    if os.path.exists(PY):
        ok('Entorno virtual (.venv) ya existe')
        return
    info('Creando entorno virtual por primera vez (puede tardar unos segundos)...')
    try:
        venv.create(VENV_DIR, with_pip=True, clear=False)
        ok('Entorno virtual creado')
    except Exception as e:
        err(f'Error creando entorno virtual: {e}')
        _pause_exit(1)

def install_deps():
    if os.path.exists(REQ_FILE):
        info('Instalando desde requirements.txt...')
        cmd = [PIP, 'install', '-q', '--upgrade', '-r', REQ_FILE]
    else:
        info('Instalando Flask...')
        cmd = [PIP, 'install', '-q', '--upgrade', 'flask']

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        err('Error instalando dependencias:')
        print(r.stderr[:500])
        _pause_exit(1)
    ok('Dependencias listas')

def _pause_exit(code=0):
    if IS_WIN:
        print('\n  Pulsa INTRO para cerrar...')
        input()
    sys.exit(code)

# ── OPEN BROWSER ──────────────────────────────────────────────────────────────
def _open_browser():
    """Espera a que Flask arranque y abre el navegador."""
    for _ in range(30):           # max ~6 s
        time.sleep(0.2)
        if port_in_use(PORT):
            break
    time.sleep(0.4)               # pequeño margen extra
    webbrowser.open(URL)

# ── RUN APP ───────────────────────────────────────────────────────────────────
def run_app():
    sep()
    print(_c('1;38;5;208', f'''
  ┌─────────────────────────────────────────┐
  │   🏗  ObraPasaLista está corriendo      │
  │   Abre tu navegador en:                 │
  │   {URL:<38} │
  │                                         │
  │   Cierra esta ventana para parar        │
  └─────────────────────────────────────────┘
'''))

    env = os.environ.copy()
    env['FLASK_ENV']   = 'production'
    env['FLASK_DEBUG'] = '0'

    threading.Thread(target=_open_browser, daemon=True).start()

    try:
        subprocess.run([PY, APP_FILE], cwd=BASE_DIR, env=env)
    except KeyboardInterrupt:
        pass
    except FileNotFoundError:
        err(f'No se puede ejecutar: {PY}')
        err('Borra la carpeta .venv y vuelve a ejecutar el launcher.')
        _pause_exit(1)

    print()
    info('ObraPasaLista detenido. ¡Hasta pronto!')
    _pause_exit(0)

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    enable_ansi()

    print(_c('1;38;5;208', r"""
  ╔══════════════════════════════════════════╗
  ║   🏗   ObraPasaLista  v1.0               ║
  ║        Control de presencia en obra      ║
  ╚══════════════════════════════════════════╝"""))

    # ── Comprobar si ya hay una instancia corriendo
    if port_in_use(PORT):
        warn(f'Puerto {PORT} ya en uso — probablemente ya está corriendo.')
        info(f'Abriendo {URL} en el navegador...')
        webbrowser.open(URL)
        _pause_exit(0)

    hdr('Comprobaciones previas')
    sep()
    check_python()
    check_app()

    hdr('Entorno virtual')
    sep()
    create_venv()

    hdr('Dependencias')
    sep()
    install_deps()

    hdr('Arrancando servidor')
    run_app()


if __name__ == '__main__':
    main()