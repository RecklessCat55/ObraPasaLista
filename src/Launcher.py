#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ObraPasaLista — Launcher v1.1
Doble clic en start.bat (Windows) o: python3 Launcher.py
"""
import sys, os, subprocess, time, webbrowser, venv, platform, threading, socket, shutil
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
PORT      = 5000
URL       = f'http://127.0.0.1:{PORT}'
BASE_DIR  = Path(__file__).resolve().parent
DB_PATH   = BASE_DIR / 'app.db'
VENV_DIR  = BASE_DIR / '.venv'
APP_FILE  = BASE_DIR / 'app.py'
REQ_FILE  = BASE_DIR / 'requirements.txt'
IS_WIN    = platform.system() == 'Windows'
BIN       = VENV_DIR / ('Scripts' if IS_WIN else 'bin')
PY        = BIN / ('python.exe' if IS_WIN else 'python')
PIP       = BIN / ('pip.exe'    if IS_WIN else 'pip')
FLASK     = BIN / ('flask.exe'  if IS_WIN else 'flask')

# ── COLORES ANSI ──────────────────────────────────────────────────────────────
os.system('')  # habilita ANSI en Windows cmd/PowerShell
def _c(code, t): return f'\033[{code}m{t}\033[0m'
def ok(t):   print(_c('92',       f'  ✓  {t}'))
def info(t): print(_c('96',       f'  →  {t}'))
def warn(t): print(_c('93',       f'  ⚠  {t}'))
def err(t):  print(_c('91',       f'  ✗  {t}'))
def hdr(t):  print(_c('1;38;5;208', f'\n  {t}'))
def sep():   print(_c('90', '  ' + '─' * 46))

def banner():
    print(_c('1;38;5;208', r"""
  ╔════════════════════════════════════════════╗
  ║  🏗  ObraPasaLista  v1.1                   ║
  ║      Control de presencia en obra          ║
  ╚════════════════════════════════════════════╝"""))

def pause_exit(code=0):
    if IS_WIN:
        print('\n  Pulsa INTRO para cerrar...')
        input()
    sys.exit(code)

# ── CHECKS ────────────────────────────────────────────────────────────────────
def check_python():
    v = sys.version_info
    if v < (3, 8):
        err(f'Necesitas Python 3.8+. Versión actual: {v.major}.{v.minor}')
        err('Descarga Python en https://python.org')
        pause_exit(1)
    ok(f'Python {v.major}.{v.minor}.{v.micro}')

def check_app():
    if not APP_FILE.exists():
        err(f'No se encuentra app.py en:')
        err(f'  {BASE_DIR}')
        err('Asegúrate de que Launcher.py y app.py están en la misma carpeta.')
        pause_exit(1)
    ok('app.py encontrado')

# ── ENTORNO VIRTUAL ───────────────────────────────────────────────────────────
def create_venv():
    if PY.exists():
        ok('Entorno virtual (.venv) ya existe')
        return
    info('Creando entorno virtual (primera vez, puede tardar unos segundos)...')
    try:
        venv.create(str(VENV_DIR), with_pip=True, clear=False)
        ok('Entorno virtual creado')
    except Exception as e:
        err(f'Error creando entorno virtual: {e}')
        pause_exit(1)

def install_deps():
    if REQ_FILE.exists():
        info('Instalando dependencias desde requirements.txt...')
        cmd = [str(PIP), 'install', '-q', '--upgrade', '-r', str(REQ_FILE)]
    else:
        info('Instalando Flask...')
        cmd = [str(PIP), 'install', '-q', '--upgrade', 'flask']
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        err('Error instalando dependencias:')
        print(r.stderr[:600])
        pause_exit(1)
    ok('Dependencias listas')

# ── BASE DE DATOS ─────────────────────────────────────────────────────────────
def setup_db():
    """Inicializa la BD si es nueva, o migra si es v1.0."""
    env = _flask_env()

    if not DB_PATH.exists():
        # Instalación limpia
        info('Primera ejecución — inicializando base de datos...')
        r = subprocess.run(
            [str(PY), '-m', 'flask', '--app', 'app', 'init-db'],
            cwd=str(BASE_DIR), env=env, capture_output=True, text=True)
        if r.returncode == 0:
            ok('Base de datos inicializada (v1.1)')
        else:
            warn(f'init-db retornó error (puede ignorarse si la BD ya existe):\n  {r.stderr[:300]}')
    else:
        # BD existente → intentar migración
        info('Ejecutando migración v1.0 → v1.1 (seguro si ya está migrada)...')
        r = subprocess.run(
            [str(PY), '-m', 'flask', '--app', 'app', 'upgrade-db'],
            cwd=str(BASE_DIR), env=env, capture_output=True, text=True)
        if r.returncode == 0:
            ok('Base de datos lista (migración aplicada)')
        else:
            # upgrade-db falla silenciosamente si las columnas ya existen
            # (el propio comando lo gestiona), solo mostramos si hay error real
            if 'error' in r.stderr.lower() and 'already exists' not in r.stderr.lower():
                warn(f'upgrade-db: {r.stderr[:200]}')
            else:
                ok('Base de datos lista')

def _flask_env():
    e = os.environ.copy()
    e['FLASK_ENV']   = 'production'
    e['FLASK_DEBUG'] = '0'
    return e

# ── ARRANQUE ──────────────────────────────────────────────────────────────────
def port_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', PORT)) == 0

def open_browser():
    for _ in range(40):       # espera hasta 8 s
        time.sleep(0.2)
        if port_in_use(): break
    time.sleep(0.5)
    webbrowser.open(URL)

def run_app():
    sep()
    print(_c('1;38;5;208', f"""
  ┌──────────────────────────────────────────────┐
  │  🏗  ObraPasaLista v1.1 está corriendo        │
  │                                              │
  │  Abre tu navegador en:                       │
  │  {URL:<46} │
  │                                              │
  │  Cierra esta ventana para parar la app       │
  └──────────────────────────────────────────────┘
"""))
    threading.Thread(target=open_browser, daemon=True).start()
    try:
        subprocess.run([str(PY), str(APP_FILE)], cwd=str(BASE_DIR), env=_flask_env())
    except KeyboardInterrupt:
        pass
    except FileNotFoundError:
        err(f'No se puede ejecutar {PY}')
        err('Borra la carpeta .venv y vuelve a ejecutar el Launcher.')
        pause_exit(1)
    print()
    info('ObraPasaLista detenido. ¡Hasta pronto!')
    pause_exit(0)

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    banner()

    # ¿Ya está corriendo?
    if port_in_use():
        warn(f'Puerto {PORT} ya en uso — ObraPasaLista probablemente ya está corriendo.')
        info(f'Abriendo {URL} en el navegador...')
        webbrowser.open(URL)
        pause_exit(0)

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

    hdr('Base de datos')
    sep()
    setup_db()

    hdr('Arrancando servidor')
    run_app()

if __name__ == '__main__':
    main()