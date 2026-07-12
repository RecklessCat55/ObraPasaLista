#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ObraPasaLista v1.2
pip install flask
python app.py  ->  http://127.0.0.1:5000
flask --app app init-db     (instalación limpia)
flask --app app upgrade-db  (migración desde v1.0/v1.1)

Variables de entorno soportadas:
  OBRAPL_MODE      'prod' (por defecto) o 'test' -> selecciona app.db / app_test.db
  OBRAPL_DOCS_DIR  ruta alternativa para la carpeta de documentación (docs/)
  SECRET_KEY       clave de sesion Flask (si no se define, se genera una aleatoria)
"""
import os, sqlite3, shutil, calendar, unicodedata, re, csv, io, json, mimetypes
from datetime import datetime, date as date_type
from jinja2 import DictLoader
from flask import (Flask, g, render_template_string, request,
                   redirect, url_for, flash, Response, send_file, abort)
import click
from werkzeug.utils import secure_filename

from services.fechas import nf, fs, mes, dia, hhmm, norm
from services import horas as _horas_svc
from services.logs import log_event as _log_event_svc

# -- RUTAS / MODO DE ENTORNO (2.1) --
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

MODE    = os.environ.get("OBRAPL_MODE", "prod")
DB_NAME = "app_test.db" if MODE == "test" else "app.db"
DB_PATH = os.path.join(DATA_DIR, DB_NAME)
BACKUP_DIR = os.path.join(DATA_DIR, "backups")

# Documentacion por obra/partida (3.3)
DOCS_DIR = os.environ.get("OBRAPL_DOCS_DIR") or os.path.join(BASE_DIR, "docs")
os.makedirs(DOCS_DIR, exist_ok=True)


def _migrar_ubicacion_bd_legacy():
    """
    Compatibilidad con instalaciones v1.1: si existe una BD en la ubicacion
    antigua (src/app.db, src/backups/) y todavia no hay nada en data/, se
    mueven automaticamente. Solo aplica al modo 'prod' con nombre por defecto.
    """
    if MODE != 'prod':
        return
    legacy_db = os.path.join(BASE_DIR, 'app.db')
    if os.path.exists(legacy_db) and not os.path.exists(DB_PATH):
        try:
            shutil.move(legacy_db, DB_PATH)
        except Exception:
            pass
    legacy_bk = os.path.join(BASE_DIR, 'backups')
    if os.path.isdir(legacy_bk) and not os.path.isdir(BACKUP_DIR):
        try:
            shutil.move(legacy_bk, BACKUP_DIR)
        except Exception:
            pass


_migrar_ubicacion_bd_legacy()

app = Flask(__name__)
import secrets
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(16)
app.config.update(DATABASE=DB_PATH)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 64 MB por subida de documentacion

# -- SCHEMA COMPLETO v1.1 --
SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS empresa(
    id_empresa INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    estado TEXT NOT NULL DEFAULT 'activa',
    meta_horas_dia REAL);

CREATE TABLE IF NOT EXISTS empresa_relacion(
    id_rel INTEGER PRIMARY KEY AUTOINCREMENT,
    id_empresa_principal    INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT,
    id_empresa_subcontrata  INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT,
    tipo_relacion TEXT NOT NULL DEFAULT 'subcontrata',
    fecha_inicio DATE, fecha_fin DATE,
    UNIQUE(id_empresa_principal, id_empresa_subcontrata));

CREATE TABLE IF NOT EXISTS rango(
    id_rango INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '');

CREATE TABLE IF NOT EXISTS persona(
    id_persona INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL, apellido1 TEXT NOT NULL,
    apellido2 TEXT NOT NULL DEFAULT '', dni TEXT NOT NULL UNIQUE,
    id_empresa INTEGER REFERENCES empresa(id_empresa) ON UPDATE CASCADE ON DELETE SET NULL,
    oficio TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'activa',
    meta_horas_dia REAL,
    precio_hora_override REAL);

CREATE TABLE IF NOT EXISTS persona_rango(
    id_pr INTEGER PRIMARY KEY AUTOINCREMENT,
    id_persona INTEGER NOT NULL REFERENCES persona(id_persona) ON DELETE CASCADE,
    id_rango   INTEGER NOT NULL REFERENCES rango(id_rango)   ON DELETE RESTRICT,
    fecha_inicio DATE NOT NULL, fecha_fin DATE);

CREATE TABLE IF NOT EXISTS obra(
    id_obra INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activa',
    meta_horas_dia REAL);

CREATE TABLE IF NOT EXISTS obra_empresa(
    id_oe INTEGER PRIMARY KEY AUTOINCREMENT,
    id_obra    INTEGER NOT NULL REFERENCES obra(id_obra)       ON DELETE RESTRICT,
    id_empresa INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT,
    rol TEXT NOT NULL DEFAULT 'principal',
    UNIQUE(id_obra, id_empresa));

CREATE TABLE IF NOT EXISTS partida_obra(
    id_partida INTEGER PRIMARY KEY AUTOINCREMENT,
    id_obra    INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE CASCADE,
    codigo TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '',
    UNIQUE(id_obra, codigo));

CREATE TABLE IF NOT EXISTS config(
    id_config INTEGER PRIMARY KEY,
    limite_horas_dia REAL NOT NULL DEFAULT 24.0 CHECK(limite_horas_dia>0),
    umbral_desajuste_meta REAL NOT NULL DEFAULT 2.0 CHECK(umbral_desajuste_meta>=0));

-- v1.2: tarifas por rango, para informes de coste (3.2)
CREATE TABLE IF NOT EXISTS tarifa_rango(
    id_rango INTEGER PRIMARY KEY REFERENCES rango(id_rango) ON DELETE CASCADE,
    precio_hora REAL NOT NULL CHECK(precio_hora >= 0));

-- v1.2: documentacion por obra/partida (3.3)
CREATE TABLE IF NOT EXISTS carpeta_obra(
    id_carpeta   INTEGER PRIMARY KEY AUTOINCREMENT,
    id_obra      INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE RESTRICT,
    id_partida   INTEGER REFERENCES partida_obra(id_partida) ON DELETE SET NULL,
    nombre       TEXT    NOT NULL,
    ruta_relativa TEXT   NOT NULL,
    id_padre     INTEGER REFERENCES carpeta_obra(id_carpeta) ON DELETE CASCADE,
    archivada    INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS archivo_obra(
    id_archivo   INTEGER PRIMARY KEY AUTOINCREMENT,
    id_carpeta   INTEGER NOT NULL REFERENCES carpeta_obra(id_carpeta) ON DELETE CASCADE,
    nombre       TEXT    NOT NULL,
    ruta_relativa TEXT   NOT NULL,
    tipo_mime    TEXT,
    fecha_subida TEXT    NOT NULL,
    notas        TEXT);

-- v1.2: auditoria de acciones administrativas sobre obras (2.3)
CREATE TABLE IF NOT EXISTS log_auditoria(
    id_log      INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha       TEXT    NOT NULL,
    tipo_evento TEXT    NOT NULL,
    entidad     TEXT    NOT NULL,
    entidad_id  INTEGER NOT NULL,
    obra_id     INTEGER NOT NULL,
    detalle     TEXT    NOT NULL);

CREATE TABLE IF NOT EXISTS diario(
    id_diario INTEGER PRIMARY KEY AUTOINCREMENT,
    id_obra INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE RESTRICT,
    fecha DATE NOT NULL,
    meteo_estado  TEXT NOT NULL DEFAULT 'soleado',
    meteo_detalle TEXT NOT NULL DEFAULT '',
    meteo_temp_c  REAL,
    UNIQUE(id_obra, fecha));

CREATE TABLE IF NOT EXISTS diario_linea(
    id_dl INTEGER PRIMARY KEY AUTOINCREMENT,
    id_diario  INTEGER NOT NULL REFERENCES diario(id_diario)          ON DELETE CASCADE,
    id_empresa INTEGER NOT NULL REFERENCES empresa(id_empresa)         ON DELETE RESTRICT,
    id_persona INTEGER NOT NULL REFERENCES persona(id_persona)         ON DELETE RESTRICT,
    id_rango   INTEGER          REFERENCES rango(id_rango)             ON DELETE SET NULL,
    id_partida INTEGER          REFERENCES partida_obra(id_partida)    ON DELETE SET NULL,
    asunto TEXT NOT NULL DEFAULT '',
    horas REAL NOT NULL DEFAULT 0 CHECK(horas>=0 AND horas<=24));

CREATE TABLE IF NOT EXISTS mensual(
    id_mensual INTEGER PRIMARY KEY AUTOINCREMENT,
    id_obra    INTEGER NOT NULL REFERENCES obra(id_obra)       ON DELETE RESTRICT,
    id_empresa INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT,
    mes TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'abierto',
    UNIQUE(id_obra, id_empresa, mes));

CREATE TABLE IF NOT EXISTS mensual_persona(
    id_mp INTEGER PRIMARY KEY AUTOINCREMENT,
    id_mensual INTEGER NOT NULL REFERENCES mensual(id_mensual)  ON DELETE CASCADE,
    id_persona INTEGER NOT NULL REFERENCES persona(id_persona)  ON DELETE RESTRICT,
    id_rango   INTEGER          REFERENCES rango(id_rango)      ON DELETE SET NULL,
    id_empresa INTEGER          REFERENCES empresa(id_empresa)  ON DELETE SET NULL,
    nom_c TEXT NOT NULL, ap1_c TEXT NOT NULL, ap2_c TEXT NOT NULL DEFAULT '',
    dni_c TEXT NOT NULL, rango_cache TEXT NOT NULL DEFAULT '',
    empresa_cache TEXT NOT NULL DEFAULT '',
    es_subcontrata INTEGER NOT NULL DEFAULT 0,
    d1  REAL, d2  REAL, d3  REAL, d4  REAL, d5  REAL, d6  REAL, d7  REAL,
    d8  REAL, d9  REAL, d10 REAL, d11 REAL, d12 REAL, d13 REAL, d14 REAL,
    d15 REAL, d16 REAL, d17 REAL, d18 REAL, d19 REAL, d20 REAL, d21 REAL,
    d22 REAL, d23 REAL, d24 REAL, d25 REAL, d26 REAL, d27 REAL, d28 REAL,
    d29 REAL, d30 REAL, d31 REAL,
    total_mes REAL NOT NULL DEFAULT 0);
"""

RANGOS_DEFAULT = [
    ('SIN_ESPECIFICAR','Sin especificar','Rango no asignado'),
    ('PEON',  'Peón',       'Trabajador no cualificado'),
    ('OF2',   'Oficial 2ª', 'Oficial de segunda'),
    ('OF1',   'Oficial 1ª', 'Oficial de primera'),
    ('CAPAZ', 'Capataz',    'Encargado de cuadrilla'),
    ('ENCARG','Encargado',  'Encargado de obra'),
]

# -- MIGRACIÓN v1.0 -> v1.1 --
MIGRATION_V11 = [
    "CREATE TABLE IF NOT EXISTS rango(id_rango INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '')",
    "CREATE TABLE IF NOT EXISTS persona_rango(id_pr INTEGER PRIMARY KEY AUTOINCREMENT, id_persona INTEGER NOT NULL REFERENCES persona(id_persona) ON DELETE CASCADE, id_rango INTEGER NOT NULL REFERENCES rango(id_rango) ON DELETE RESTRICT, fecha_inicio DATE NOT NULL, fecha_fin DATE)",
    "CREATE TABLE IF NOT EXISTS empresa_relacion(id_rel INTEGER PRIMARY KEY AUTOINCREMENT, id_empresa_principal INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT, id_empresa_subcontrata INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT, tipo_relacion TEXT NOT NULL DEFAULT 'subcontrata', fecha_inicio DATE, fecha_fin DATE, UNIQUE(id_empresa_principal, id_empresa_subcontrata))",
    "CREATE TABLE IF NOT EXISTS partida_obra(id_partida INTEGER PRIMARY KEY AUTOINCREMENT, id_obra INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE CASCADE, codigo TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '', UNIQUE(id_obra, codigo))",
    "ALTER TABLE diario ADD COLUMN meteo_estado  TEXT NOT NULL DEFAULT 'soleado'",
    "ALTER TABLE diario ADD COLUMN meteo_detalle TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE diario ADD COLUMN meteo_temp_c  REAL",
    "ALTER TABLE diario_linea ADD COLUMN id_rango   INTEGER REFERENCES rango(id_rango) ON DELETE SET NULL",
    "ALTER TABLE diario_linea ADD COLUMN id_partida INTEGER REFERENCES partida_obra(id_partida) ON DELETE SET NULL",
    "ALTER TABLE mensual_persona ADD COLUMN id_rango       INTEGER REFERENCES rango(id_rango) ON DELETE SET NULL",
    "ALTER TABLE mensual_persona ADD COLUMN id_empresa     INTEGER REFERENCES empresa(id_empresa) ON DELETE SET NULL",
    "ALTER TABLE mensual_persona ADD COLUMN rango_cache    TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE mensual_persona ADD COLUMN empresa_cache  TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE mensual_persona ADD COLUMN es_subcontrata INTEGER NOT NULL DEFAULT 0",
]

# -- MIGRACIÓN v1.1 -> v1.2 (ver secciones 2.3, 3.1, 3.2, 3.3 del doc de cambios) --
MIGRATION_V12 = [
    # 3.1 metas de horas
    "ALTER TABLE persona ADD COLUMN meta_horas_dia REAL",
    "ALTER TABLE empresa ADD COLUMN meta_horas_dia REAL",
    "ALTER TABLE obra    ADD COLUMN meta_horas_dia REAL",
    "ALTER TABLE config  ADD COLUMN umbral_desajuste_meta REAL NOT NULL DEFAULT 2.0 CHECK(umbral_desajuste_meta >= 0)",
    # 3.2 tarifas y costes
    "CREATE TABLE IF NOT EXISTS tarifa_rango(id_rango INTEGER PRIMARY KEY REFERENCES rango(id_rango) ON DELETE CASCADE, precio_hora REAL NOT NULL CHECK(precio_hora >= 0))",
    "ALTER TABLE persona ADD COLUMN precio_hora_override REAL",
    # 3.3 documentación por obra/partida
    "CREATE TABLE IF NOT EXISTS carpeta_obra(id_carpeta INTEGER PRIMARY KEY AUTOINCREMENT, id_obra INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE RESTRICT, id_partida INTEGER REFERENCES partida_obra(id_partida) ON DELETE SET NULL, nombre TEXT NOT NULL, ruta_relativa TEXT NOT NULL, id_padre INTEGER REFERENCES carpeta_obra(id_carpeta) ON DELETE CASCADE, archivada INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS archivo_obra(id_archivo INTEGER PRIMARY KEY AUTOINCREMENT, id_carpeta INTEGER NOT NULL REFERENCES carpeta_obra(id_carpeta) ON DELETE CASCADE, nombre TEXT NOT NULL, ruta_relativa TEXT NOT NULL, tipo_mime TEXT, fecha_subida TEXT NOT NULL, notas TEXT)",
    # 2.3 auditoría
    "CREATE TABLE IF NOT EXISTS log_auditoria(id_log INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, tipo_evento TEXT NOT NULL, entidad TEXT NOT NULL, entidad_id INTEGER NOT NULL, obra_id INTEGER NOT NULL, detalle TEXT NOT NULL)",
    "ALTER TABLE log_auditoria ADD COLUMN obra_id INTEGER",  # por si la tabla ya existía sin esta columna
]

# -- DB HELPERS --
def get_db():
    if 'db' not in g:
        conn = sqlite3.connect(app.config['DATABASE'], detect_types=0)
        conn.execute('PRAGMA foreign_keys=ON')
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    d = g.pop('db', None)
    if d: d.close()

def _seed_rangos(db):
    for cod, nom, desc in RANGOS_DEFAULT:
        db.execute('INSERT OR IGNORE INTO rango(codigo,nombre,descripcion) VALUES(?,?,?)', [cod, nom, desc])
    db.commit()

@app.cli.command('init-db')
def cli_init_db():
    """Crea la BD desde cero (instalación limpia, ya en v1.2)."""
    db = get_db()
    db.executescript(SCHEMA)
    db.execute('INSERT OR IGNORE INTO config(id_config,limite_horas_dia,umbral_desajuste_meta) VALUES(1,24.0,2.0)')
    db.commit()
    _seed_rangos(db)
    click.echo('OK BD inicializada (v1.2).')

def _aplicar_migracion(db, statements, etiqueta):
    for stmt in statements:
        try:
            db.execute(stmt)
            db.commit()
        except Exception as e:
            msg = str(e).lower()
            if 'duplicate column' in msg or 'already exists' in msg:
                pass  # ya estaba migrado
            else:
                click.echo(f'  ADVERTENCIA ({etiqueta}) {e}')

@app.cli.command('upgrade-db')
def cli_upgrade_db():
    """Migra una BD v1.0/v1.1 existente hasta v1.2 (idempotente)."""
    db = get_db()
    _aplicar_migracion(db, MIGRATION_V11, 'v1.1')
    _aplicar_migracion(db, MIGRATION_V12, 'v1.2')
    # config puede no tener aún la fila con id_config=1 en instalaciones muy antiguas
    db.execute('INSERT OR IGNORE INTO config(id_config,limite_horas_dia,umbral_desajuste_meta) VALUES(1,24.0,2.0)')
    db.commit()
    _seed_rangos(db)
    # Asignar SIN_ESPECIFICAR a personas sin historial de rango
    sin = db.execute("SELECT id_rango FROM rango WHERE codigo='SIN_ESPECIFICAR'").fetchone()
    if sin:
        for p in db.execute("SELECT id_persona FROM persona").fetchall():
            if not db.execute("SELECT 1 FROM persona_rango WHERE id_persona=?", [p['id_persona']]).fetchone():
                db.execute("INSERT INTO persona_rango(id_persona,id_rango,fecha_inicio) VALUES(?,?,'2000-01-01')",
                           [p['id_persona'], sin['id_rango']])
        db.commit()
    click.echo('OK Migración v1.2 completada.')

# -- BUSINESS HELPERS --
# hhmm() y norm() viven ahora en services/fechas.py (importados arriba).
#
# get_lim / chk_horas / chk_mes_cerrado / get_rango_activo eran lógica de
# negocio duplicada en cada ruta; a partir de v1.2 la implementación real
# vive en services/horas.py (punto 2.2 del doc de cambios) y aquí quedan
# solo wrappers finos que atan esa lógica a la conexión de BD de la request
# actual (get_db()), para no tener que tocar todas las rutas que ya los usan.
def get_lim():
    return _horas_svc.get_lim(get_db())

def chk_horas(id_p, fecha, h_new, excl=None):
    return _horas_svc.chk_horas(id_p, fecha, h_new, get_db(), excl=excl)

def chk_mes_cerrado(id_obra, id_emp, fecha):
    return _horas_svc.chk_mes_cerrado(id_obra, id_emp, fecha, get_db())

def get_rango_activo(id_persona, fecha):
    return _horas_svc.get_rango_activo(id_persona, fecha, get_db())

def log_event(tipo_evento, entidad, entidad_id, obra_id, detalle_dict):
    """Wrapper de services.logs.log_event atado a get_db()/flash() (punto 2.3)."""
    return _log_event_svc(get_db(), tipo_evento, entidad, entidad_id, obra_id, detalle_dict, flash_fn=flash)

def get_subcontratas(id_empresa):
    rows = get_db().execute(
        "SELECT id_empresa_subcontrata FROM empresa_relacion WHERE id_empresa_principal=?",
        [id_empresa]).fetchall()
    return [r['id_empresa_subcontrata'] for r in rows]

def _calcular_filas_mensual(id_obra, id_empresa, mes_str):
    """Calcula filas del mensual desde los diarios (estado abierto)."""
    db = get_db()
    subs = get_subcontratas(id_empresa)
    emp_ids = [id_empresa] + subs
    ph = ','.join(['?'] * len(emp_ids))
    rows = db.execute(f"""
        SELECT dl.id_persona, dl.id_empresa, dl.id_rango,
               p.nombre nom_c, p.apellido1 ap1_c, p.apellido2 ap2_c, p.dni dni_c,
               e.nombre emp_n, r.nombre ran_n,
               CAST(strftime('%d', d.fecha) AS INTEGER) ndia,
               SUM(dl.horas) horas
        FROM diario_linea dl
        JOIN diario   d ON dl.id_diario  = d.id_diario
        JOIN persona  p ON dl.id_persona = p.id_persona
        JOIN empresa  e ON dl.id_empresa = e.id_empresa
        LEFT JOIN rango r ON dl.id_rango = r.id_rango
        WHERE d.id_obra=? AND dl.id_empresa IN ({ph})
          AND strftime('%Y-%m', d.fecha)=?
        GROUP BY dl.id_persona, dl.id_empresa, dl.id_rango, ndia
        ORDER BY e.nombre, p.apellido1, p.nombre, ndia""",
                      [id_obra] + emp_ids + [mes_str]).fetchall()

    grupos = {}
    for r in rows:
        k = (r['id_persona'], r['id_empresa'], r['id_rango'])
        if k not in grupos:
            grupos[k] = dict(nom_c=r['nom_c'], ap1_c=r['ap1_c'], ap2_c=r['ap2_c'],
                             dni_c=r['dni_c'], empresa_cache=r['emp_n'],
                             rango_cache=r['ran_n'] or '',
                             es_subcontrata=1 if r['id_empresa'] != id_empresa else 0,
                             id_persona=r['id_persona'], id_empresa=r['id_empresa'],
                             id_rango=r['id_rango'], dias={})
        grupos[k]['dias'][r['ndia']] = r['horas']

    year, month = int(mes_str[:4]), int(mes_str[5:])
    days = calendar.monthrange(year, month)[1]
    result = []
    for k, g in grupos.items():
        dias_arr = [g['dias'].get(i) for i in range(1, days+1)]
        total = sum(h for h in dias_arr if h is not None)
        result.append({**g, 'dias_arr': dias_arr, 'total_mes': total, 'days': days})
    result.sort(key=lambda x: (x['es_subcontrata'], x['empresa_cache'], x['ap1_c'], x['nom_c']))
    return result, days

# ============================ METAS DE HORAS (3.1, 4.4) =====================
def get_meta_efectiva(id_persona, id_empresa, id_obra):
    """
    Meta de horas/día efectiva: persona > empresa > obra > 8h por defecto.
    Devuelve (valor, origen) donde origen in {'persona','empresa','obra','defecto'}.
    """
    db = get_db()
    if id_persona:
        r = db.execute('SELECT meta_horas_dia FROM persona WHERE id_persona=?', [id_persona]).fetchone()
        if r and r['meta_horas_dia'] is not None:
            return r['meta_horas_dia'], 'persona'
    if id_empresa:
        r = db.execute('SELECT meta_horas_dia FROM empresa WHERE id_empresa=?', [id_empresa]).fetchone()
        if r and r['meta_horas_dia'] is not None:
            return r['meta_horas_dia'], 'empresa'
    if id_obra:
        r = db.execute('SELECT meta_horas_dia FROM obra WHERE id_obra=?', [id_obra]).fetchone()
        if r and r['meta_horas_dia'] is not None:
            return r['meta_horas_dia'], 'obra'
    return 8.0, 'defecto'

def get_umbral_desajuste():
    r = get_db().execute('SELECT umbral_desajuste_meta FROM config WHERE id_config=1').fetchone()
    return r['umbral_desajuste_meta'] if r else 2.0

def chk_desajuste_meta(id_persona, id_empresa):
    """
    Devuelve un mensaje de aviso (str) si la meta de la persona y la de su
    empresa difieren en más del umbral configurado, o None si no aplica.
    No bloquea nada: es solo informativo, para mostrarse en 'momentos clave'
    (vincular persona a empresa, informes...), no en cada fichaje.
    """
    db = get_db()
    p = db.execute('SELECT meta_horas_dia, nombre, apellido1 FROM persona WHERE id_persona=?', [id_persona]).fetchone()
    e = db.execute('SELECT meta_horas_dia, nombre FROM empresa WHERE id_empresa=?', [id_empresa]).fetchone()
    if not p or not e or p['meta_horas_dia'] is None or e['meta_horas_dia'] is None:
        return None
    umbral = get_umbral_desajuste()
    diff = abs(p['meta_horas_dia'] - e['meta_horas_dia'])
    if diff >= umbral:
        return (f"Desajuste de meta: {p['nombre']} {p['apellido1']} tiene meta {hhmm(p['meta_horas_dia'])} "
                f"pero {e['nombre']} tiene meta {hhmm(e['meta_horas_dia'])} (diferencia {hhmm(diff)}).")
    return None

def _listar_desajustes_meta():
    """Recorre todas las personas con empresa asignada y devuelve la lista de avisos de desajuste."""
    db = get_db()
    avisos = []
    for p in db.execute("SELECT id_persona, id_empresa FROM persona WHERE id_empresa IS NOT NULL AND estado='activa'").fetchall():
        w = chk_desajuste_meta(p['id_persona'], p['id_empresa'])
        if w: avisos.append(w)
    return avisos

# ============================ COSTES (3.2, 4.5) ==============================
def _precio_efectivo_persona(id_persona, fecha=None):
    """Precio/hora efectivo = persona.precio_hora_override si existe, si no tarifa_rango de su rango activo."""
    db = get_db()
    p = db.execute('SELECT precio_hora_override FROM persona WHERE id_persona=?', [id_persona]).fetchone()
    if p and p['precio_hora_override'] is not None:
        return p['precio_hora_override']
    fecha = fecha or fs(date_type.today())
    id_r = get_rango_activo(id_persona, fecha)
    if id_r:
        t = db.execute('SELECT precio_hora FROM tarifa_rango WHERE id_rango=?', [id_r]).fetchone()
        if t: return t['precio_hora']
    return None

def _informe_costes(id_obra, mes_str):
    """
    Calcula, para una obra y un mes:
      - filas: coste total por persona y mes (usa snapshot si el mensual de
        su empresa está cerrado, o el diario si sigue abierto).
      - dias_tabla: coste total por obra/día (agregado de todas las personas).
    Los costes NUNCA se almacenan; se recalculan bajo demanda con los precios
    vigentes en el momento de generar el informe.
    """
    db = get_db()
    year, month = int(mes_str[:4]), int(mes_str[5:])
    days = calendar.monthrange(year, month)[1]
    cerrados = {r['id_empresa'] for r in db.execute(
        "SELECT id_empresa FROM mensual WHERE id_obra=? AND mes=? AND estado='cerrado'",
        [id_obra, mes_str]).fetchall()}

    filas = []
    horas_dia = [0.0] * (days + 1)
    coste_dia = [0.0] * (days + 1)

    # -- empresas con mensual ya cerrado: snapshot mensual_persona --
    dcols = ','.join(f'mp.d{i}' for i in range(1, 32))
    for r in db.execute(f"""SELECT mp.id_persona, mp.nom_c, mp.ap1_c, mp.ap2_c, mp.empresa_cache, mp.total_mes, {dcols}
                            FROM mensual_persona mp JOIN mensual m ON mp.id_mensual=m.id_mensual
                            WHERE m.id_obra=? AND m.mes=? AND m.estado='cerrado'""",
                         [id_obra, mes_str]).fetchall():
        precio = _precio_efectivo_persona(r['id_persona']) or 0
        horas = r['total_mes'] or 0
        filas.append(dict(nombre=f"{r['ap1_c']} {r['ap2_c']}, {r['nom_c']}", empresa=r['empresa_cache'],
                           horas=horas, precio_hora=precio, coste=horas * precio))
        for i in range(1, days + 1):
            h = r[f'd{i}']
            if h:
                horas_dia[i] += h
                coste_dia[i] += h * precio

    # -- empresas con mensual abierto (o sin mensual): directamente del diario --
    q = """SELECT dl.id_persona, dl.id_empresa, p.nombre nom, p.apellido1 ap1, p.apellido2 ap2, e.nombre emp,
                  CAST(strftime('%d', d.fecha) AS INTEGER) ndia, SUM(dl.horas) horas
           FROM diario_linea dl
           JOIN diario  d ON dl.id_diario=d.id_diario
           JOIN persona p ON dl.id_persona=p.id_persona
           JOIN empresa e ON dl.id_empresa=e.id_empresa
           WHERE d.id_obra=? AND strftime('%Y-%m', d.fecha)=?"""
    params = [id_obra, mes_str]
    if cerrados:
        q += f" AND dl.id_empresa NOT IN ({','.join(['?']*len(cerrados))})"
        params += list(cerrados)
    q += " GROUP BY dl.id_persona, dl.id_empresa, ndia"

    agg = {}
    for r in db.execute(q, params).fetchall():
        k = (r['id_persona'], r['id_empresa'])
        if k not in agg:
            agg[k] = dict(nombre=f"{r['ap1']} {r['ap2']}, {r['nom']}", empresa=r['emp'],
                          horas=0.0, precio_hora=_precio_efectivo_persona(r['id_persona']) or 0)
        agg[k]['horas'] += r['horas']
        horas_dia[r['ndia']] += r['horas']
        coste_dia[r['ndia']] += r['horas'] * agg[k]['precio_hora']
    for v in agg.values():
        v['coste'] = v['horas'] * v['precio_hora']
        filas.append(v)

    filas.sort(key=lambda x: (x['empresa'], x['nombre']))
    total_horas = sum(f['horas'] for f in filas)
    total_coste = sum(f['coste'] for f in filas)
    dias_tabla = [{'dia': i, 'horas': horas_dia[i], 'coste': coste_dia[i]} for i in range(1, days + 1)]
    return filas, dias_tabla, total_horas, total_coste, days

# ==================== ESTADO DE OBRA / AUDITORÍA (2.3, 4.1, 5) ================
def _chk_obra_activa(id_obra):
    """Lanza ValueError si la obra está finalizada (para bloquear altas/bajas)."""
    ob = get_db().execute('SELECT estado FROM obra WHERE id_obra=?', [id_obra]).fetchone()
    if ob and ob['estado'] == 'finalizada':
        raise ValueError('La obra está finalizada: esta acción no está permitida.')

def _mensuales_abiertos(id_obra):
    """Lista de mensuales en estado 'abierto' para una obra (cualquier empresa)."""
    return get_db().execute("""SELECT m.*, e.nombre nom_e FROM mensual m
        JOIN empresa e ON m.id_empresa=e.id_empresa
        WHERE m.id_obra=? AND m.estado='abierto' ORDER BY m.mes, e.nombre""", [id_obra]).fetchall()

# ============================ DOCUMENTACIÓN (3.3, 4.6) ========================
def _ruta_carpeta_obra(id_obra, nombre_carpeta, id_carpeta):
    """Ruta relativa (dentro de DOCS_DIR) de una carpeta nueva."""
    return os.path.join(f'obra_{id_obra}', f'carpeta_{id_carpeta}_{secure_filename(nombre_carpeta) or "carpeta"}')

def _archivar_docs_partida(id_obra, id_partida):
    """
    Mueve físicamente a docs/archivado/... toda la documentación asociada a
    una partida (y sus subcarpetas) y marca esas carpetas como archivadas.
    Se llama ANTES de borrar la partida: la FK id_partida de carpeta_obra es
    ON DELETE SET NULL, así que al borrar la partida SQLite limpia esa
    referencia automáticamente. Devuelve el nº de archivos movidos.
    """
    db = get_db()
    carpetas_raiz = db.execute(
        "SELECT * FROM carpeta_obra WHERE id_partida=? AND archivada=0", [id_partida]).fetchall()
    if not carpetas_raiz:
        return 0
    fecha_tag = datetime.now().strftime('%Y%m%d_%H%M%S')
    destino_rel_base = os.path.join('archivado', f'obra_{id_obra}', f'partida_{id_partida}_{fecha_tag}')
    os.makedirs(os.path.join(DOCS_DIR, destino_rel_base), exist_ok=True)

    # BFS: carpeta raíz + todas sus subcarpetas
    todas = []
    pendientes = list(carpetas_raiz)
    while pendientes:
        c = pendientes.pop()
        todas.append(c)
        pendientes.extend(db.execute(
            "SELECT * FROM carpeta_obra WHERE id_padre=? AND archivada=0", [c['id_carpeta']]).fetchall())

    n_archivos = 0
    for c in todas:
        origen_abs = os.path.join(DOCS_DIR, c['ruta_relativa'])
        destino_rel = os.path.join(destino_rel_base, os.path.basename(c['ruta_relativa']))
        destino_abs = os.path.join(DOCS_DIR, destino_rel)
        try:
            if os.path.isdir(origen_abs) and not os.path.exists(destino_abs):
                os.makedirs(os.path.dirname(destino_abs), exist_ok=True)
                shutil.move(origen_abs, destino_abs)
        except Exception:
            pass  # si ya no está en disco, seguimos para dejar la BD consistente
        archivos = db.execute("SELECT * FROM archivo_obra WHERE id_carpeta=?", [c['id_carpeta']]).fetchall()
        for a in archivos:
            nueva_ruta = os.path.join(destino_rel, os.path.basename(a['ruta_relativa']))
            db.execute("UPDATE archivo_obra SET ruta_relativa=? WHERE id_archivo=?", [nueva_ruta, a['id_archivo']])
            n_archivos += 1
        db.execute("UPDATE carpeta_obra SET ruta_relativa=?, archivada=1 WHERE id_carpeta=?", [destino_rel, c['id_carpeta']])
    return n_archivos

def _init_if_needed():
    db = get_db()
    # Crea tablas si no existen (primer arranque sin CLI)
    db.executescript(SCHEMA)
    # Si la BD viene de una v1.1 sin pasar por `upgrade-db`, aplicamos también
    # la migración v1.2 aquí (todos los statements son idempotentes).
    _aplicar_migracion(db, MIGRATION_V12, 'v1.2 (auto)')
    if not db.execute("SELECT 1 FROM config WHERE id_config=1").fetchone():
        db.execute('INSERT OR IGNORE INTO config(id_config,limite_horas_dia,umbral_desajuste_meta) VALUES(1,24.0,2.0)')
        db.commit()
    _seed_rangos(db)

@app.context_processor
def inject_globals():
    return {'hoy': fs(date_type.today())}

# ================================ TEMPLATES ================================

_BASE_HTML = r"""<!DOCTYPE html>
<html lang="es" data-bs-theme="dark">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{% block title %}OPL{% endblock %} — ObraPasaLista</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.2/css/bootstrap.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap-icons/1.11.3/font/bootstrap-icons.min.css">
<style>
body{background:#0d1117}
.navbar-brand{color:#f97316!important;font-weight:800}
.btn-opl{background:#f97316;border-color:#f97316;color:#fff}
.btn-opl:hover,.btn-opl:focus{background:#c2410c;border-color:#c2410c;color:#fff}
.nav-link.hi{color:#f97316!important;font-weight:600}
.card{border-color:#30363d}.card-header{background:#161b22;border-color:#30363d}
.sec{color:#f97316;font-weight:700;border-bottom:2px solid #30363d;padding-bottom:.3rem;margin-bottom:.9rem;font-size:.95rem}
.htd{text-align:center;font-family:monospace;font-size:.75rem;padding:2px 3px!important;min-width:38px}
.hth{text-align:center;font-size:.7rem;padding:3px 2px!important;min-width:38px}
.badge-activa,.badge-abierto{background:#22c55e!important}
.badge-inactiva,.badge-finalizada,.badge-baja,.badge-cerrado{background:#6b7280!important}
.table-sm td,.table-sm th{font-size:.83rem}
</style></head>
<body>
<nav class="navbar navbar-expand-lg bg-body-tertiary border-bottom border-secondary-subtle mb-3 py-1">
<div class="container-fluid">
  <a class="navbar-brand" href="/"><i class="bi bi-building-fill"></i> ObraPasaLista
    <span class="badge bg-secondary fw-light ms-1" style="font-size:.55rem">v1.2</span>
  </a>
  <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#nb">
    <span class="navbar-toggler-icon"></span>
  </button>
  <div class="collapse navbar-collapse" id="nb">
    <ul class="navbar-nav me-auto">
      <li class="nav-item"><a class="nav-link {% block ah %}{% endblock %}" href="/"><i class="bi bi-house"></i> Inicio</a></li>
      <li class="nav-item"><a class="nav-link {% block ad %}{% endblock %}" href="/diario/"><i class="bi bi-calendar-day"></i> Diario</a></li>
      <li class="nav-item"><a class="nav-link {% block am %}{% endblock %}" href="/mensual/"><i class="bi bi-calendar-month"></i> Mensual</a></li>
      <li class="nav-item dropdown">
        <a class="nav-link dropdown-toggle {% block amae %}{% endblock %}" href="#" data-bs-toggle="dropdown">
          <i class="bi bi-database"></i> Maestros
        </a>
        <ul class="dropdown-menu dropdown-menu-dark">
          <li><a class="dropdown-item" href="/obras/"><i class="bi bi-buildings"></i> Obras</a></li>
          <li><a class="dropdown-item" href="/empresas/"><i class="bi bi-briefcase"></i> Empresas</a></li>
          <li><a class="dropdown-item" href="/personas/"><i class="bi bi-people"></i> Personas</a></li>
          <li><hr class="dropdown-divider"></li>
          <li><a class="dropdown-item" href="/rangos/"><i class="bi bi-award"></i> Rangos</a></li>
          <li><a class="dropdown-item" href="/subcontratas/"><i class="bi bi-diagram-3"></i> Subcontratas</a></li>
        </ul>
      </li>
      <li class="nav-item dropdown">
        <a class="nav-link dropdown-toggle {% block ain %}{% endblock %}" href="#" data-bs-toggle="dropdown">
          <i class="bi bi-graph-up"></i> Informes
        </a>
        <ul class="dropdown-menu dropdown-menu-dark">
          <li><a class="dropdown-item" href="/informes/costes"><i class="bi bi-cash-coin"></i> Costes</a></li>
        </ul>
      </li>
    </ul>
    <ul class="navbar-nav">
      <li class="nav-item"><a class="nav-link" href="/backup/"><i class="bi bi-hdd"></i> Backup</a></li>
      <li class="nav-item dropdown">
        <a class="nav-link dropdown-toggle {% block ac %}{% endblock %}" href="#" data-bs-toggle="dropdown">
          <i class="bi bi-gear"></i> Config
        </a>
        <ul class="dropdown-menu dropdown-menu-dark dropdown-menu-end">
          <li><a class="dropdown-item" href="/config/"><i class="bi bi-sliders"></i> General</a></li>
          <li><a class="dropdown-item" href="/config/metas"><i class="bi bi-bullseye"></i> Metas de horas</a></li>
        </ul>
      </li>
      <li class="nav-item"><a class="nav-link {% block af %}{% endblock %}" href="/faq/"><i class="bi bi-question-circle"></i> FAQ</a></li>
    </ul>
  </div>
</div>
</nav>
<div class="container-fluid px-4">
{% with msgs=get_flashed_messages(with_categories=True) %}
{% for cat,msg in msgs %}
<div class="alert alert-{{ 'danger' if cat=='error' else ('success' if cat=='success' else ('warning' if cat=='warning' else 'info')) }} alert-dismissible fade show py-2">
  {{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
</div>
{% endfor %}{% endwith %}
{% block content %}{% endblock %}
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.2/js/bootstrap.bundle.min.js"></script>
{% block scripts %}{% endblock %}
</body></html>"""

app.jinja_env.loader = DictLoader({'_base.html': _BASE_HTML})
BASE = '{% extends "_base.html" %}'

# ================================= RUTAS ====================================

# -- HOME --
@app.route('/')
def index():
    _init_if_needed()
    db = get_db()
    obras = db.execute("SELECT * FROM obra WHERE estado='activa' ORDER BY nombre").fetchall()
    return render_template_string(BASE + r"""
{% block ah %}hi{% endblock %}{% block title %}Inicio{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h2 class="h4 mb-0"><i class="bi bi-house"></i> Panel de control</h2>
  <span class="text-muted small"><i class="bi bi-calendar3"></i> Hoy: <strong>{{ hoy }}</strong></span>
</div>
<div class="row g-3 mb-4">
  {% for ico,col,val,lab in stats %}
  <div class="col-6 col-md-3"><div class="card text-center"><div class="card-body py-3">
    <div class="fs-2 text-{{ col }}"><i class="bi bi-{{ ico }}"></i></div>
    <div class="fs-3 fw-bold">{{ val }}</div><small class="text-muted">{{ lab }}</small>
  </div></div></div>
  {% endfor %}
</div>
<div class="sec"><i class="bi bi-calendar-day"></i> Parte de hoy — acceso rápido</div>
<div class="row g-2">
{% for ob in obras %}
<div class="col-md-4 col-xl-3"><div class="card"><div class="card-body py-2">
  <div class="d-flex justify-content-between align-items-center mb-2">
    <span class="fw-semibold">{{ ob.nombre }}</span>
    <span class="badge bg-secondary">{{ ob.codigo }}</span>
  </div>
  <a href="/diario/{{ ob.id_obra }}/{{ hoy }}" class="btn btn-opl btn-sm w-100">
    <i class="bi bi-calendar-day"></i> Abrir parte
  </a>
</div></div></div>
{% else %}
<div class="col"><div class="alert alert-info">Sin obras activas. <a href="/obras/nueva">Crea una obra</a>.</div></div>
{% endfor %}
</div>
{% endblock %}
""", obras=obras, stats=[
        ('buildings','warning', db.execute("SELECT count(*) FROM obra WHERE estado='activa'").fetchone()[0], 'Obras activas'),
        ('briefcase','info',    db.execute("SELECT count(*) FROM empresa WHERE estado='activa'").fetchone()[0], 'Empresas'),
        ('people','success',   db.execute("SELECT count(*) FROM persona WHERE estado='activa'").fetchone()[0], 'Personas activas'),
        ('clock','',           hhmm(get_lim()), 'Límite h/día'),
    ])

# -- EMPRESAS --
@app.route('/empresas/')
def empresas():
    db = get_db()
    rows = db.execute("""SELECT e.*,
        (SELECT count(*) FROM persona WHERE id_empresa=e.id_empresa) n_p,
        (SELECT count(*) FROM obra_empresa WHERE id_empresa=e.id_empresa) n_o
        FROM empresa e ORDER BY e.nombre""").fetchall()
    return render_template_string(BASE + r"""
{% block amae %}hi{% endblock %}{% block title %}Empresas{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h2 class="h4 mb-0"><i class="bi bi-briefcase"></i> Empresas</h2>
  <a href="/empresas/nueva" class="btn btn-opl btn-sm"><i class="bi bi-plus"></i> Nueva</a>
</div>
<div class="card"><div class="card-body p-0"><table class="table table-hover mb-0 table-sm">
  <thead><tr><th>Nombre</th><th>Estado</th><th>Personas</th><th>Obras</th><th class="text-end">Acciones</th></tr></thead>
  <tbody>
  {% for e in emps %}
  <tr>
    <td class="fw-semibold">{{ e.nombre }}</td>
    <td><span class="badge badge-{{ e.estado }}">{{ e.estado }}</span></td>
    <td>{{ e.n_p }}</td><td>{{ e.n_o }}</td>
    <td class="text-end">
      <a href="/empresas/{{ e.id_empresa }}/editar" class="btn btn-sm btn-outline-secondary py-0"><i class="bi bi-pencil"></i></a>
      <form method="post" action="/empresas/{{ e.id_empresa }}/eliminar" class="d-inline"
            onsubmit="return confirm('¿Eliminar empresa {{ e.nombre }}?')">
        <button class="btn btn-sm btn-outline-danger py-0"><i class="bi bi-trash"></i></button>
      </form>
    </td>
  </tr>
  {% else %}
  <tr><td colspan="5" class="text-center py-4 text-muted">Sin empresas.</td></tr>
  {% endfor %}
  </tbody>
</table></div></div>
{% endblock %}
""", emps=rows)

@app.route('/empresas/nueva', methods=['GET','POST'])
def empresa_nueva():
    if request.method == 'POST':
        nom = request.form['nombre'].strip()
        if not nom: flash('Nombre obligatorio.', 'error'); return redirect(url_for('empresa_nueva'))
        try:
            get_db().execute('INSERT INTO empresa(nombre) VALUES(?)', [nom]); get_db().commit()
            flash(f'Empresa "{nom}" creada.', 'success'); return redirect(url_for('empresas'))
        except Exception as e: flash(f'Error: {e}', 'error')
    return render_template_string(BASE + _EMP_FORM, emp=None)

@app.route('/empresas/<int:id_>/editar', methods=['GET','POST'])
def empresa_editar(id_):
    db = get_db()
    emp = db.execute('SELECT * FROM empresa WHERE id_empresa=?', [id_]).fetchone()
    if not emp: flash('No encontrada.', 'error'); return redirect(url_for('empresas'))
    if request.method == 'POST':
        nom, est = request.form['nombre'].strip(), request.form['estado']
        meta_raw = request.form.get('meta_horas_dia', '').strip()
        meta = None
        if not nom: flash('Nombre obligatorio.', 'error')
        else:
            try:
                if meta_raw:
                    meta = float(meta_raw)
                    if meta <= 0: raise ValueError('La meta debe ser mayor que 0.')
                db.execute('UPDATE empresa SET nombre=?,estado=?,meta_horas_dia=? WHERE id_empresa=?', [nom,est,meta,id_])
                db.commit(); flash('Actualizada.', 'success'); return redirect(url_for('empresas'))
            except ValueError as e: flash(f'Meta de horas inválida: {e}', 'error')
            except Exception as e: flash(f'Error: {e}', 'error')
    return render_template_string(BASE + _EMP_FORM, emp=emp)

@app.route('/empresas/<int:id_>/eliminar', methods=['POST'])
def empresa_eliminar(id_):
    db = get_db()
    try:
        e = db.execute('SELECT nombre FROM empresa WHERE id_empresa=?', [id_]).fetchone()
        db.execute('DELETE FROM empresa WHERE id_empresa=?', [id_]); db.commit()
        flash(f'Empresa "{e["nombre"]}" eliminada.', 'success')
    except: flash('No se puede eliminar: hay registros vinculados.', 'error')
    return redirect(url_for('empresas'))

_EMP_FORM = r"""
{% block amae %}hi{% endblock %}
{% block title %}{{ 'Editar' if emp else 'Nueva' }} empresa{% endblock %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-5">
<div class="card"><div class="card-header"><h5 class="mb-0">{{ 'Editar' if emp else 'Nueva' }} empresa</h5></div>
<div class="card-body">
<form method="post">
  <div class="mb-3"><label class="form-label">Nombre *</label>
    <input type="text" name="nombre" class="form-control" value="{{ emp.nombre if emp else '' }}" required autofocus></div>
  {% if emp %}
  <div class="mb-3"><label class="form-label">Estado</label>
    <select name="estado" class="form-select">
      <option value="activa" {{ 'selected' if emp.estado=='activa' }}>Activa</option>
      <option value="finalizada" {{ 'selected' if emp.estado=='finalizada' }}>Finalizada</option>
      <option value="baja" {{ 'selected' if emp.estado=='baja' }}>Baja</option>
    </select></div>
  <div class="mb-3"><label class="form-label">Meta de horas/día <span class="text-muted small">(opcional)</span></label>
    <input type="number" name="meta_horas_dia" class="form-control" step="0.25" min="0.25"
           value="{{ emp.meta_horas_dia if emp.meta_horas_dia is not none else '' }}"
           placeholder="Usar meta por obra / 8h por defecto">
    <div class="form-text">Se usa si la persona no tiene meta propia. Editable en <a href="/config/metas">Config → Metas de horas</a>.</div>
  </div>
  {% endif %}
  <div class="d-flex gap-2">
    <button type="submit" class="btn btn-opl">Guardar</button>
    <a href="/empresas/" class="btn btn-secondary">Cancelar</a>
  </div>
</form></div></div></div></div>
{% endblock %}"""

# -- SUBCONTRATAS --
@app.route('/subcontratas/')
def subcontratas():
    db = get_db()
    rels = db.execute("""SELECT r.*, ep.nombre nom_p, es.nombre nom_s
        FROM empresa_relacion r
        JOIN empresa ep ON r.id_empresa_principal=ep.id_empresa
        JOIN empresa es ON r.id_empresa_subcontrata=es.id_empresa
        ORDER BY ep.nombre, es.nombre""").fetchall()
    emps = db.execute("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").fetchall()
    return render_template_string(BASE + r"""
{% block amae %}hi{% endblock %}{% block title %}Subcontratas{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h2 class="h4 mb-0"><i class="bi bi-diagram-3"></i> Subcontratas</h2>
  <a href="/empresas/" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left"></i> Empresas</a>
</div>
<div class="row g-3">
<div class="col-md-4">
  <div class="card"><div class="card-header">Nueva relación</div><div class="card-body">
  <p class="small text-muted">Define que empresa A subcontrata a empresa B. El mensual de A incluirá a los trabajadores de B.</p>
  <form method="post" action="/subcontratas/nueva">
    <div class="mb-2"><label class="form-label small">Empresa principal</label>
      <select name="id_principal" class="form-select form-select-sm" required>
        <option value="">— Selecciona —</option>
        {% for e in emps %}<option value="{{ e.id_empresa }}">{{ e.nombre }}</option>{% endfor %}
      </select></div>
    <div class="mb-3"><label class="form-label small">Subcontrata (empresa B)</label>
      <select name="id_sub" class="form-select form-select-sm" required>
        <option value="">— Selecciona —</option>
        {% for e in emps %}<option value="{{ e.id_empresa }}">{{ e.nombre }}</option>{% endfor %}
      </select></div>
    <button type="submit" class="btn btn-opl btn-sm w-100">Añadir relación</button>
  </form></div></div>
</div>
<div class="col-md-8">
  <div class="card"><div class="card-body p-0">
  <table class="table table-hover mb-0 table-sm">
    <thead><tr><th>Principal</th><th>Subcontrata</th><th class="text-end">Acción</th></tr></thead>
    <tbody>
    {% for r in rels %}
    <tr>
      <td>{{ r.nom_p }}</td><td>{{ r.nom_s }}</td>
      <td class="text-end">
        <form method="post" action="/subcontratas/{{ r.id_rel }}/eliminar" class="d-inline"
              onsubmit="return confirm('¿Eliminar relación?')">
          <button class="btn btn-sm btn-outline-danger py-0"><i class="bi bi-x"></i></button>
        </form>
      </td>
    </tr>
    {% else %}
    <tr><td colspan="3" class="text-center py-3 text-muted">Sin relaciones definidas.</td></tr>
    {% endfor %}
    </tbody>
  </table></div></div>
</div></div>
{% endblock %}
""", rels=rels, emps=emps)

@app.route('/subcontratas/nueva', methods=['POST'])
def subcontrata_nueva():
    ip = request.form.get('id_principal', type=int)
    iss = request.form.get('id_sub', type=int)
    if not ip or not iss or ip == iss:
        flash('Selecciona empresas distintas.', 'error')
    else:
        try:
            get_db().execute('INSERT OR IGNORE INTO empresa_relacion(id_empresa_principal,id_empresa_subcontrata) VALUES(?,?)', [ip,iss])
            get_db().commit(); flash('Relación añadida.', 'success')
        except Exception as e: flash(f'Error: {e}', 'error')
    return redirect(url_for('subcontratas'))

@app.route('/subcontratas/<int:id_>/eliminar', methods=['POST'])
def subcontrata_eliminar(id_):
    get_db().execute('DELETE FROM empresa_relacion WHERE id_rel=?', [id_]); get_db().commit()
    flash('Relación eliminada.', 'success'); return redirect(url_for('subcontratas'))

# -- RANGOS --
@app.route('/rangos/')
def rangos():
    rows = get_db().execute("""SELECT r.*,
        (SELECT count(*) FROM persona_rango WHERE id_rango=r.id_rango) n_hist,
        (SELECT count(*) FROM diario_linea  WHERE id_rango=r.id_rango) n_diario,
        (SELECT count(*) FROM mensual_persona WHERE id_rango=r.id_rango) n_mensual,
        (SELECT precio_hora FROM tarifa_rango WHERE id_rango=r.id_rango) precio_hora
        FROM rango r ORDER BY r.codigo""").fetchall()
    return render_template_string(BASE + r"""
{% block amae %}hi{% endblock %}{% block title %}Rangos{% endblock %}
{% block content %}
<h2 class="h4 mb-3"><i class="bi bi-award"></i> Rangos profesionales</h2>
<div class="row g-3">
<div class="col-md-4">
  <div class="card"><div class="card-header">Nuevo rango</div><div class="card-body">
  <form method="post" action="/rangos/nuevo">
    <div class="mb-2"><label class="form-label small">Código *</label>
      <input type="text" name="codigo" class="form-control form-control-sm" placeholder="OF1, PEON..." required></div>
    <div class="mb-2"><label class="form-label small">Nombre *</label>
      <input type="text" name="nombre" class="form-control form-control-sm" required></div>
    <div class="mb-3"><label class="form-label small">Descripción</label>
      <input type="text" name="descripcion" class="form-control form-control-sm"></div>
    <button type="submit" class="btn btn-opl btn-sm w-100">Crear</button>
  </form></div></div>
</div>
<div class="col-md-8">
  <div class="card"><div class="card-body p-0">
  <table class="table table-hover mb-0 table-sm align-middle">
    <thead><tr><th>Código</th><th>Nombre</th><th>Descripción</th><th title="Personas con este rango en su historial">Uso</th><th>Precio/h (€)</th><th></th></tr></thead>
    <tbody>
    {% for r in rangos %}
    {% set en_uso = r.n_hist + r.n_diario + r.n_mensual %}
    {% set protegido = r.codigo == 'SIN_ESPECIFICAR' %}
    <tr>
      <td class="font-monospace fw-bold">{{ r.codigo }}
        {% if protegido %}<span class="badge bg-secondary" style="font-size:.6rem" title="Rango de sistema, usado como valor por defecto">sistema</span>{% endif %}
      </td>
      <td>{{ r.nombre }}</td>
      <td class="text-muted">{{ r.descripcion }}</td>
      <td>
        {% if en_uso %}
        <span class="badge bg-warning text-dark" title="Historial: {{ r.n_hist }} · Diario: {{ r.n_diario }} · Mensual: {{ r.n_mensual }}">
          {{ en_uso }} registro(s)</span>
        {% else %}
        <span class="text-muted small">sin uso</span>
        {% endif %}
      </td>
      <td>
        <form method="post" action="/rangos/{{ r.id_rango }}/tarifa" class="d-flex gap-1">
          <input type="number" name="precio_hora" class="form-control form-control-sm" step="0.01" min="0"
                 style="width:90px" value="{{ r.precio_hora if r.precio_hora is not none else '' }}" placeholder="—">
          <button class="btn btn-sm btn-outline-secondary py-0"><i class="bi bi-check"></i></button>
        </form>
      </td>
      <td class="text-end">
        {% if protegido %}
        <button class="btn btn-sm btn-outline-secondary py-0 disabled" title="Rango de sistema: no se puede eliminar" disabled>
          <i class="bi bi-trash"></i></button>
        {% elif en_uso %}
        <button class="btn btn-sm btn-outline-secondary py-0 disabled"
                title="En uso ({{ en_uso }} registro(s)): reasigna esas personas/líneas a otro rango antes de poder eliminarlo" disabled>
          <i class="bi bi-trash"></i></button>
        {% else %}
        <form method="post" action="/rangos/{{ r.id_rango }}/eliminar" class="d-inline"
              onsubmit="return confirm('¿Eliminar el rango {{ r.codigo }}? No tiene ningún uso registrado, así que es seguro, pero no se puede deshacer.')">
          <button class="btn btn-sm btn-outline-danger py-0"><i class="bi bi-trash"></i></button>
        </form>
        {% endif %}
      </td>
    </tr>
    {% endfor %}
    </tbody>
  </table></div></div>
  <p class="text-muted small mt-2"><i class="bi bi-info-circle"></i> El precio/hora de un rango se usa en
    <a href="/informes/costes">Informes → Costes</a> salvo que la persona tenga un precio propio
    (<em>override</em>) definido en su ficha. No se muestra en el diario ni en el mensual operativo.
    Solo se puede eliminar un rango si no tiene ningún uso registrado (ni en el historial de personas, ni en
    partes diarios, ni en mensuales cerrados); en caso contrario, reasigna primero esos registros a otro rango.</p>
</div></div>
{% endblock %}
""", rangos=rows)

@app.route('/rangos/nuevo', methods=['POST'])
def rango_nuevo():
    cod = request.form['codigo'].strip().upper()
    nom = request.form['nombre'].strip()
    desc = request.form.get('descripcion','').strip()
    if not cod or not nom: flash('Código y nombre obligatorios.', 'error')
    else:
        try:
            get_db().execute('INSERT INTO rango(codigo,nombre,descripcion) VALUES(?,?,?)', [cod,nom,desc])
            get_db().commit(); flash(f'Rango {cod} creado.', 'success')
        except Exception as e: flash(f'Error: {e}', 'error')
    return redirect(url_for('rangos'))

@app.route('/rangos/<int:id_rango>/eliminar', methods=['POST'])
def rango_eliminar(id_rango):
    """
    Borrado seguro de un rango: nunca deja huérfanos ni rompe el histórico.
    Se bloquea si el rango tiene cualquier uso (historial de personas, líneas
    de diario o snapshots de mensual) o si es el rango de sistema
    'SIN_ESPECIFICAR' (usado como valor por defecto en toda la app).
    """
    db = get_db()
    r = db.execute('SELECT * FROM rango WHERE id_rango=?', [id_rango]).fetchone()
    if not r:
        flash('Rango no encontrado.', 'error'); return redirect(url_for('rangos'))
    if r['codigo'] == 'SIN_ESPECIFICAR':
        flash('"Sin especificar" es el rango por defecto del sistema y no se puede eliminar.', 'error')
        return redirect(url_for('rangos'))

    n_hist    = db.execute('SELECT count(*) n FROM persona_rango WHERE id_rango=?', [id_rango]).fetchone()['n']
    n_diario  = db.execute('SELECT count(*) n FROM diario_linea  WHERE id_rango=?', [id_rango]).fetchone()['n']
    n_mensual = db.execute('SELECT count(*) n FROM mensual_persona WHERE id_rango=?', [id_rango]).fetchone()['n']
    if n_hist or n_diario or n_mensual:
        flash(f'No se puede eliminar "{r["codigo"]}": está en uso ({n_hist} en historial de personas, '
             f'{n_diario} en líneas de diario, {n_mensual} en snapshots mensuales cerrados). '
             f'Reasigna esos registros a otro rango antes de eliminarlo.', 'error')
        return redirect(url_for('rangos'))

    try:
        db.execute('DELETE FROM tarifa_rango WHERE id_rango=?', [id_rango])  # por claridad; ON DELETE CASCADE ya lo haría
        db.execute('DELETE FROM rango WHERE id_rango=?', [id_rango])
        db.commit()
        flash(f'Rango "{r["codigo"]}" eliminado.', 'success')
    except sqlite3.IntegrityError:
        # red de seguridad adicional por si algo lo referencia y no lo habíamos contado arriba
        db.rollback()
        flash(f'No se puede eliminar "{r["codigo"]}": todavía hay registros que lo referencian.', 'error')
    return redirect(url_for('rangos'))

@app.route('/rangos/<int:id_rango>/tarifa', methods=['POST'])
def rango_tarifa(id_rango):
    db = get_db()
    raw = request.form.get('precio_hora','').strip()
    try:
        if not raw:
            db.execute('DELETE FROM tarifa_rango WHERE id_rango=?', [id_rango])
            flash('Tarifa eliminada (sin precio definido para este rango).', 'success')
        else:
            precio = float(raw)
            if precio < 0: raise ValueError
            db.execute('INSERT INTO tarifa_rango(id_rango,precio_hora) VALUES(?,?) '
                       'ON CONFLICT(id_rango) DO UPDATE SET precio_hora=excluded.precio_hora', [id_rango, precio])
            flash('Tarifa actualizada.', 'success')
        db.commit()
    except ValueError:
        flash('Precio/hora inválido.', 'error')
    return redirect(url_for('rangos'))

# -- PERSONAS --
@app.route('/personas/')
def personas():
    db = get_db()
    q  = request.args.get('q','').strip()
    ie = request.args.get('id_empresa','').strip()
    sql = """SELECT p.*, e.nombre nom_e,
        (SELECT r.nombre FROM persona_rango pr JOIN rango r ON pr.id_rango=r.id_rango
         WHERE pr.id_persona=p.id_persona AND pr.fecha_fin IS NULL
         ORDER BY pr.fecha_inicio DESC LIMIT 1) rango_actual
        FROM persona p LEFT JOIN empresa e ON p.id_empresa=e.id_empresa WHERE 1=1"""
    params = []
    if q:
        sql += " AND (p.nombre||' '||p.apellido1||' '||p.apellido2||' '||p.dni||' '||p.oficio LIKE ?)"
        params.append(f'%{q}%')
    if ie: sql += " AND p.id_empresa=?"; params.append(ie)
    sql += " ORDER BY p.apellido1, p.nombre"
    pers = db.execute(sql, params).fetchall()
    emps = db.execute("SELECT * FROM empresa ORDER BY nombre").fetchall()
    return render_template_string(BASE + r"""
{% block amae %}hi{% endblock %}{% block title %}Personas{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
  <h2 class="h4 mb-0"><i class="bi bi-people"></i> Personas</h2>
  <div class="d-flex gap-2 flex-wrap">
    <form method="get" class="d-flex gap-2 align-items-center">
      <input type="text" name="q" value="{{ q }}" class="form-control form-control-sm" placeholder="Buscar..." style="width:170px">
      <select name="id_empresa" class="form-select form-select-sm" style="width:160px">
        <option value="">Todas las empresas</option>
        {% for e in emps %}<option value="{{ e.id_empresa }}" {{ 'selected' if ie==e.id_empresa|string }}>{{ e.nombre }}</option>{% endfor %}
      </select>
      <button class="btn btn-sm btn-secondary"><i class="bi bi-search"></i></button>
    </form>
    <a href="/personas/nueva" class="btn btn-opl btn-sm"><i class="bi bi-plus"></i> Nueva</a>
  </div>
</div>
<div class="card"><div class="card-body p-0">
<table class="table table-hover mb-0 table-sm">
  <thead><tr><th>Apellidos, Nombre</th><th>DNI</th><th>Empresa</th><th>Rango</th><th>Estado</th><th class="text-end">Acc.</th></tr></thead>
  <tbody>
  {% for p in pers %}
  <tr>
    <td>{{ p.apellido1 }} {{ p.apellido2 }}, {{ p.nombre }}</td>
    <td class="font-monospace">{{ p.dni }}</td>
    <td>{{ p.nom_e or '—' }}</td>
    <td><span class="badge bg-secondary" style="font-size:.7rem">{{ p.rango_actual or 'SIN_ESPECIFICAR' }}</span></td>
    <td><span class="badge badge-{{ p.estado }}">{{ p.estado }}</span></td>
    <td class="text-end">
      <a href="/personas/{{ p.id_persona }}/editar" class="btn btn-sm btn-outline-secondary py-0"><i class="bi bi-pencil"></i></a>
      <form method="post" action="/personas/{{ p.id_persona }}/eliminar" class="d-inline"
            onsubmit="return confirm('¿Eliminar {{ p.nombre }}?')">
        <button class="btn btn-sm btn-outline-danger py-0"><i class="bi bi-trash"></i></button>
      </form>
    </td>
  </tr>
  {% else %}
  <tr><td colspan="6" class="text-center py-4 text-muted">Sin personas.</td></tr>
  {% endfor %}
  </tbody>
</table></div></div>
{% endblock %}
""", pers=pers, emps=emps, q=q, ie=ie)

@app.route('/personas/nueva', methods=['GET','POST'])
def persona_nueva():
    db = get_db()
    emps   = db.execute("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").fetchall()
    rangos = db.execute("SELECT * FROM rango WHERE codigo!='SIN_ESPECIFICAR' ORDER BY codigo").fetchall()
    if request.method == 'POST':
        f = request.form
        nom, ap1, ap2 = f['nombre'].strip(), f['apellido1'].strip(), f.get('apellido2','').strip()
        dni, ide, ofi = f['dni'].strip(), f.get('id_empresa') or None, f.get('oficio','').strip()
        idr = f.get('id_rango') or None
        errs = []
        if not nom: errs.append('Nombre')
        if not ap1: errs.append('Primer apellido')
        if not dni: errs.append('DNI')
        if not idr: errs.append('Rango profesional')
        if errs:
            flash(f'Campos obligatorios: {", ".join(errs)}.', 'error')
        else:
            try:
                meta_raw   = f.get('meta_horas_dia','').strip()
                precio_raw = f.get('precio_hora_override','').strip()
                meta   = float(meta_raw) if meta_raw else None
                precio = float(precio_raw) if precio_raw else None
                cur = db.execute('INSERT INTO persona(nombre,apellido1,apellido2,dni,id_empresa,oficio,meta_horas_dia,precio_hora_override) '
                                 'VALUES(?,?,?,?,?,?,?,?)',
                                 [nom,ap1,ap2,dni,ide,ofi,meta,precio])
                db.execute('INSERT INTO persona_rango(id_persona,id_rango,fecha_inicio) VALUES(?,?,?)',
                           [cur.lastrowid, idr, fs(date_type.today())])
                db.commit(); flash(f'{ap1}, {nom} creado.', 'success')
                if ide:
                    w = chk_desajuste_meta(cur.lastrowid, int(ide))
                    if w: flash(w, 'warning')
                return redirect(url_for('personas'))
            except Exception as e: flash(f'Error: {e}', 'error')
    return render_template_string(BASE + _PER_FORM, per=None, emps=emps, rangos=rangos,
                                  ra=None, hist=[])

@app.route('/personas/<int:id_>/editar', methods=['GET','POST'])
def persona_editar(id_):
    db = get_db()
    per  = db.execute('SELECT * FROM persona WHERE id_persona=?', [id_]).fetchone()
    if not per: flash('No encontrada.', 'error'); return redirect(url_for('personas'))
    emps   = db.execute("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").fetchall()
    rangos = db.execute("SELECT * FROM rango ORDER BY codigo").fetchall()
    ra     = db.execute("SELECT id_rango FROM persona_rango WHERE id_persona=? AND fecha_fin IS NULL ORDER BY fecha_inicio DESC LIMIT 1", [id_]).fetchone()
    hist   = db.execute("SELECT pr.*,r.nombre nom_r FROM persona_rango pr JOIN rango r ON pr.id_rango=r.id_rango WHERE pr.id_persona=? ORDER BY pr.fecha_inicio DESC", [id_]).fetchall()
    if request.method == 'POST':
        f = request.form
        nom, ap1, ap2 = f['nombre'].strip(), f['apellido1'].strip(), f.get('apellido2','').strip()
        dni, ide, ofi, est = f['dni'].strip(), f.get('id_empresa') or None, f.get('oficio','').strip(), f['estado']
        new_r = f.get('id_rango_nuevo') or None
        if not nom or not ap1 or not dni:
            flash('Nombre, primer apellido y DNI obligatorios.', 'error')
        else:
            try:
                meta_raw   = f.get('meta_horas_dia','').strip()
                precio_raw = f.get('precio_hora_override','').strip()
                meta   = float(meta_raw) if meta_raw else None
                precio = float(precio_raw) if precio_raw else None
                db.execute('UPDATE persona SET nombre=?,apellido1=?,apellido2=?,dni=?,id_empresa=?,oficio=?,estado=?,'
                           'meta_horas_dia=?,precio_hora_override=? WHERE id_persona=?',
                           [nom,ap1,ap2,dni,ide,ofi,est,meta,precio,id_])
                if new_r:
                    hoy_s = fs(date_type.today())
                    db.execute("UPDATE persona_rango SET fecha_fin=? WHERE id_persona=? AND fecha_fin IS NULL", [hoy_s,id_])
                    db.execute("INSERT INTO persona_rango(id_persona,id_rango,fecha_inicio) VALUES(?,?,?)", [id_,new_r,hoy_s])
                db.commit(); flash('Persona actualizada.', 'success')
                if ide:
                    w = chk_desajuste_meta(id_, int(ide))
                    if w: flash(w, 'warning')
                return redirect(url_for('personas'))
            except Exception as e: flash(f'Error: {e}', 'error')
    return render_template_string(BASE + _PER_FORM, per=per, emps=emps, rangos=rangos, ra=ra, hist=hist)

@app.route('/personas/<int:id_>/eliminar', methods=['POST'])
def persona_eliminar(id_):
    db = get_db()
    try:
        p = db.execute('SELECT nombre||" "||apellido1 n FROM persona WHERE id_persona=?', [id_]).fetchone()
        db.execute('DELETE FROM persona WHERE id_persona=?', [id_]); db.commit()
        flash(f'{p["n"]} eliminado.', 'success')
    except: flash('No se puede eliminar: tiene registros vinculados.', 'error')
    return redirect(url_for('personas'))

_PER_FORM = r"""
{% block amae %}hi{% endblock %}
{% block title %}{{ 'Editar' if per else 'Nueva' }} persona{% endblock %}
{% block content %}
<div class="row justify-content-center"><div class="col-lg-6">
<div class="card"><div class="card-header">
  <h5 class="mb-0">{{ 'Editar' if per else 'Nueva' }} persona</h5>
</div><div class="card-body">
<form method="post">
  <div class="row g-2 mb-2">
    <div class="col-6"><label class="form-label small">Nombre *</label>
      <input type="text" name="nombre" class="form-control form-control-sm" value="{{ per.nombre if per else '' }}" required autofocus></div>
    <div class="col-6"><label class="form-label small">Primer apellido *</label>
      <input type="text" name="apellido1" class="form-control form-control-sm" value="{{ per.apellido1 if per else '' }}" required></div>
  </div>
  <div class="row g-2 mb-2">
    <div class="col-6"><label class="form-label small">Segundo apellido</label>
      <input type="text" name="apellido2" class="form-control form-control-sm" value="{{ per.apellido2 if per else '' }}"></div>
    <div class="col-6"><label class="form-label small">DNI / NIE *</label>
      <input type="text" name="dni" class="form-control form-control-sm" value="{{ per.dni if per else '' }}" required></div>
  </div>
  <div class="row g-2 mb-2">
    <div class="col-6"><label class="form-label small">Empresa</label>
      <select name="id_empresa" class="form-select form-select-sm">
        <option value="">— Sin empresa —</option>
        {% for e in emps %}<option value="{{ e.id_empresa }}" {{ 'selected' if per and per.id_empresa==e.id_empresa }}>{{ e.nombre }}</option>{% endfor %}
      </select></div>
    <div class="col-6"><label class="form-label small">Oficio</label>
      <input type="text" name="oficio" class="form-control form-control-sm" value="{{ per.oficio if per else '' }}" placeholder="Chapista, Pintor..."></div>
  </div>
  <div class="row g-2 mb-2">
    <div class="col-6"><label class="form-label small">Meta de horas/día <span class="text-muted">(opc.)</span></label>
      <input type="number" name="meta_horas_dia" class="form-control form-control-sm" step="0.25" min="0.25"
             value="{{ per.meta_horas_dia if per and per.meta_horas_dia is not none else '' }}"
             placeholder="Usar meta de empresa/obra"></div>
    <div class="col-6"><label class="form-label small">Precio/hora € <span class="text-muted">(opc., override)</span></label>
      <input type="number" name="precio_hora_override" class="form-control form-control-sm" step="0.01" min="0"
             value="{{ per.precio_hora_override if per and per.precio_hora_override is not none else '' }}"
             placeholder="Usar tarifa de su rango"></div>
  </div>
  {% if per %}
  <div class="row g-2 mb-3">
    <div class="col-6"><label class="form-label small">Estado</label>
      <select name="estado" class="form-select form-select-sm">
        <option value="activa"   {{ 'selected' if per.estado=='activa' }}>Activa</option>
        <option value="inactiva" {{ 'selected' if per.estado=='inactiva' }}>Inactiva</option>
      </select></div>
    <div class="col-6"><label class="form-label small">Nuevo rango (historial)</label>
      <select name="id_rango_nuevo" class="form-select form-select-sm">
        <option value="">— Sin cambio —</option>
        {% for r in rangos %}
        <option value="{{ r.id_rango }}" {{ 'selected' if ra and r.id_rango==ra.id_rango }}>{{ r.codigo }} — {{ r.nombre }}</option>
        {% endfor %}
      </select></div>
  </div>
  {% if hist %}
  <div class="mb-3">
    <div class="sec">Historial de rangos</div>
    <table class="table table-sm table-dark mb-0" style="font-size:.75rem">
      <thead><tr><th>Rango</th><th>Desde</th><th>Hasta</th></tr></thead>
      <tbody>{% for h in hist %}
      <tr><td>{{ h.nom_r }}</td><td>{{ h.fecha_inicio }}</td><td>{{ h.fecha_fin or '(actual)' }}</td></tr>
      {% endfor %}</tbody>
    </table>
  </div>
  {% endif %}
  {% else %}
  <div class="mb-3"><label class="form-label small">Rango profesional *</label>
    <select name="id_rango" class="form-select form-select-sm" required>
      <option value="">— Selecciona —</option>
      {% for r in rangos %}<option value="{{ r.id_rango }}">{{ r.codigo }} — {{ r.nombre }}</option>{% endfor %}
    </select></div>
  {% endif %}
  <div class="d-flex gap-2">
    <button type="submit" class="btn btn-opl btn-sm">Guardar</button>
    <a href="/personas/" class="btn btn-secondary btn-sm">Cancelar</a>
  </div>
</form></div></div></div></div>
{% endblock %}"""

# -- OBRAS --
@app.route('/obras/')
def obras():
    rows = get_db().execute("SELECT * FROM obra ORDER BY estado, nombre").fetchall()
    return render_template_string(BASE + r"""
{% block amae %}hi{% endblock %}{% block title %}Obras{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h2 class="h4 mb-0"><i class="bi bi-buildings"></i> Obras</h2>
  <a href="/obras/nueva" class="btn btn-opl btn-sm"><i class="bi bi-plus"></i> Nueva obra</a>
</div>
<div class="card"><div class="card-body p-0">
<table class="table table-hover mb-0 table-sm">
  <thead><tr><th>Código</th><th>Nombre</th><th>Estado</th><th class="text-end">Acciones</th></tr></thead>
  <tbody>
  {% for o in obras %}
  <tr>
    <td class="font-monospace fw-bold">{{ o.codigo }}</td>
    <td>{{ o.nombre }}</td>
    <td><span class="badge badge-{{ o.estado }}">{{ o.estado }}</span></td>
    <td class="text-end">
      <a href="/obras/{{ o.id_obra }}/estado" class="btn btn-sm btn-outline-warning py-0" title="Estado de obra"><i class="bi bi-clipboard-data"></i></a>
      <a href="/obra/{{ o.id_obra }}/documentacion" class="btn btn-sm btn-outline-primary py-0" title="Documentación"><i class="bi bi-folder2-open"></i></a>
      <a href="/obras/{{ o.id_obra }}/editar" class="btn btn-sm btn-outline-secondary py-0"><i class="bi bi-pencil"></i></a>
      <a href="/diario/{{ o.id_obra }}/{{ hoy }}" class="btn btn-sm btn-outline-info py-0"><i class="bi bi-calendar-day"></i></a>
      <form method="post" action="/obras/{{ o.id_obra }}/eliminar" class="d-inline"
            onsubmit="return confirm('¿Eliminar obra?')">
        <button class="btn btn-sm btn-outline-danger py-0"><i class="bi bi-trash"></i></button>
      </form>
    </td>
  </tr>
  {% else %}
  <tr><td colspan="4" class="text-center py-4 text-muted">Sin obras.</td></tr>
  {% endfor %}
  </tbody>
</table></div></div>
{% endblock %}
""", obras=rows)

@app.route('/obras/nueva', methods=['GET','POST'])
def obra_nueva():
    if request.method == 'POST':
        cod, nom = request.form['codigo'].strip(), request.form['nombre'].strip()
        if not cod or not nom: flash('Código y nombre obligatorios.', 'error')
        else:
            try:
                get_db().execute('INSERT INTO obra(codigo,nombre) VALUES(?,?)', [cod,nom]); get_db().commit()
                flash(f'Obra "{nom}" creada.', 'success'); return redirect(url_for('obras'))
            except Exception as e: flash(f'Error: {e}', 'error')
    return render_template_string(BASE + _OBRA_FORM, ob=None, oes=[], emps_disp=[], parts=[])

@app.route('/obras/<int:id_>/editar', methods=['GET','POST'])
def obra_editar(id_):
    db = get_db()
    ob = db.execute('SELECT * FROM obra WHERE id_obra=?', [id_]).fetchone()
    if not ob: flash('No encontrada.', 'error'); return redirect(url_for('obras'))
    if request.method == 'POST':
        nom, cod = request.form['nombre'].strip(), request.form['codigo'].strip()
        meta_raw = request.form.get('meta_horas_dia','').strip()
        try:
            if ob['estado'] == 'finalizada' and meta_raw != (str(ob['meta_horas_dia']) if ob['meta_horas_dia'] is not None else ''):
                # las metas de una obra finalizada son de solo lectura (4.4)
                flash('La obra está finalizada: la meta de horas no es editable.', 'warning')
                meta = ob['meta_horas_dia']
            else:
                meta = float(meta_raw) if meta_raw else None
            db.execute('UPDATE obra SET nombre=?,codigo=?,meta_horas_dia=? WHERE id_obra=?', [nom,cod,meta,id_])
            db.commit(); flash('Obra actualizada.', 'success'); return redirect(url_for('obras'))
        except ValueError:
            flash('Meta de horas inválida.', 'error')
        except Exception as e: flash(f'Error: {e}', 'error')
    oes  = db.execute("SELECT oe.id_oe,e.nombre,e.id_empresa FROM obra_empresa oe JOIN empresa e ON oe.id_empresa=e.id_empresa WHERE oe.id_obra=?", [id_]).fetchall()
    disp = db.execute("SELECT * FROM empresa WHERE estado='activa' AND id_empresa NOT IN (SELECT id_empresa FROM obra_empresa WHERE id_obra=?) ORDER BY nombre", [id_]).fetchall()
    parts= db.execute("SELECT * FROM partida_obra WHERE id_obra=? ORDER BY codigo", [id_]).fetchall()
    return render_template_string(BASE + _OBRA_FORM, ob=ob, oes=oes, emps_disp=disp, parts=parts)

@app.route('/obras/<int:id_obra>/add-empresa', methods=['POST'])
def obra_add_empresa(id_obra):
    ie = request.form.get('id_empresa', type=int)
    if ie:
        try:
            get_db().execute('INSERT OR IGNORE INTO obra_empresa(id_obra,id_empresa) VALUES(?,?)', [id_obra,ie]); get_db().commit()
            flash('Empresa añadida.', 'success')
        except Exception as e: flash(f'Error: {e}', 'error')
    return redirect(url_for('obra_editar', id_=id_obra))

@app.route('/obras/<int:id_obra>/rem-empresa/<int:id_oe>', methods=['POST'])
def obra_rem_empresa(id_obra, id_oe):
    get_db().execute('DELETE FROM obra_empresa WHERE id_oe=?', [id_oe]); get_db().commit()
    flash('Empresa eliminada de la obra.', 'success'); return redirect(url_for('obra_editar', id_=id_obra))

@app.route('/obras/<int:id_obra>/add-partida', methods=['POST'])
def obra_add_partida(id_obra):
    cod = request.form['codigo'].strip()
    desc= request.form.get('descripcion','').strip()
    if not cod: flash('Código obligatorio.', 'error')
    else:
        try:
            get_db().execute('INSERT INTO partida_obra(id_obra,codigo,descripcion) VALUES(?,?,?)', [id_obra,cod,desc]); get_db().commit()
            flash(f'Partida {cod} añadida.', 'success')
        except Exception as e: flash(f'Error: {e}', 'error')
    return redirect(url_for('obra_editar', id_=id_obra))

@app.route('/obras/<int:id_obra>/rem-partida/<int:id_p>', methods=['POST'])
def obra_rem_partida(id_obra, id_p):
    db = get_db()
    part = db.execute('SELECT * FROM partida_obra WHERE id_partida=?', [id_p]).fetchone()
    try:
        n_docs = _archivar_docs_partida(id_obra, id_p) if part else 0
        if n_docs:
            log_event('DOC_ARCHIVAR_PARTIDA', 'partida', id_p, id_obra,
                     {'obra_nombre': db.execute('SELECT nombre FROM obra WHERE id_obra=?', [id_obra]).fetchone()['nombre'],
                      'partida_codigo': part['codigo'], 'n_archivos': n_docs})
        db.execute('DELETE FROM partida_obra WHERE id_partida=?', [id_p])
        db.commit()
        if n_docs:
            flash(f'Partida eliminada. Se archivaron {n_docs} archivo(s) de documentación asociados.', 'success')
        else:
            flash('Partida eliminada.', 'success')
    except Exception as e:
        flash(f'Error al eliminar la partida: {e}', 'error')
    return redirect(url_for('obra_editar', id_=id_obra))

@app.route('/obras/<int:id_>/eliminar', methods=['POST'])
def obra_eliminar(id_):
    db = get_db()
    try:
        ob = db.execute('SELECT nombre FROM obra WHERE id_obra=?', [id_]).fetchone()
        db.execute('DELETE FROM obra WHERE id_obra=?', [id_]); db.commit()
        flash(f'Obra "{ob["nombre"]}" eliminada.', 'success')
    except: flash('No se puede eliminar: tiene registros vinculados.', 'error')
    return redirect(url_for('obras'))

# -- ESTADO DE OBRA / CIERRE-REACTIVACIÓN (4.1, 5) --
@app.route('/obras/<int:id_obra>/cerrar', methods=['POST'])
def obra_cerrar(id_obra):
    db = get_db()
    ob = db.execute('SELECT * FROM obra WHERE id_obra=?', [id_obra]).fetchone()
    if not ob: flash('Obra no encontrada.', 'error'); return redirect(url_for('obras'))
    if ob['estado'] == 'finalizada':
        flash('La obra ya está finalizada.', 'warning')
        return redirect(url_for('obra_estado', id_obra=id_obra))
    abiertos = _mensuales_abiertos(id_obra)
    if abiertos:
        lista = ', '.join(f"{m['mes']} ({m['nom_e']})" for m in abiertos)
        flash(f'No se puede finalizar: hay mensuales abiertos — {lista}. Ciérralos primero.', 'error')
        return redirect(url_for('obra_estado', id_obra=id_obra))
    db.execute("UPDATE obra SET estado='finalizada' WHERE id_obra=?", [id_obra])
    log_event('CERRAR_OBRA', 'obra', id_obra, id_obra, {'obra_nombre': ob['nombre']})
    db.commit()
    flash(f'Obra "{ob["nombre"]}" finalizada.', 'success')
    return redirect(url_for('obra_estado', id_obra=id_obra))

@app.route('/obras/<int:id_obra>/reactivar', methods=['POST'])
def obra_reactivar(id_obra):
    db = get_db()
    ob = db.execute('SELECT * FROM obra WHERE id_obra=?', [id_obra]).fetchone()
    if not ob: flash('Obra no encontrada.', 'error'); return redirect(url_for('obras'))
    if ob['estado'] != 'finalizada':
        flash('La obra no está finalizada.', 'warning')
        return redirect(url_for('obra_estado', id_obra=id_obra))
    db.execute("UPDATE obra SET estado='activa' WHERE id_obra=?", [id_obra])
    log_event('REACTIVAR_OBRA', 'obra', id_obra, id_obra, {'obra_nombre': ob['nombre']})
    db.commit()
    flash(f'Obra "{ob["nombre"]}" reactivada. Los mensuales siguen cerrados hasta que los reabras explícitamente.', 'success')
    return redirect(url_for('obra_estado', id_obra=id_obra))

@app.route('/obras/<int:id_obra>/estado')
def obra_estado(id_obra):
    db = get_db()
    ob = db.execute('SELECT * FROM obra WHERE id_obra=?', [id_obra]).fetchone()
    if not ob: flash('Obra no encontrada.', 'error'); return redirect(url_for('obras'))
    mensuales = db.execute("""SELECT m.*, e.nombre nom_e FROM mensual m
        JOIN empresa e ON m.id_empresa=e.id_empresa
        WHERE m.id_obra=? ORDER BY m.mes DESC, e.nombre""", [id_obra]).fetchall()
    abiertos = [m for m in mensuales if m['estado'] == 'abierto']
    logs = db.execute("""SELECT * FROM log_auditoria WHERE obra_id=? ORDER BY id_log DESC LIMIT 30""",
                      [id_obra]).fetchall()
    logs_parsed = []
    for l in logs:
        try: detalle = json.loads(l['detalle'])
        except Exception: detalle = {}
        logs_parsed.append({**dict(l), 'detalle_obj': detalle})
    puede_finalizar = ob['estado'] == 'activa' and not abiertos
    return render_template_string(BASE + _OBRA_ESTADO_TPL, ob=ob, mensuales=mensuales,
                                  abiertos=abiertos, logs=logs_parsed, puede_finalizar=puede_finalizar)

_OBRA_ESTADO_TPL = r"""
{% block amae %}hi{% endblock %}
{% block title %}Estado {{ ob.nombre }}{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
  <div>
    <h2 class="h4 mb-0"><i class="bi bi-clipboard-data"></i> {{ ob.nombre }}
      <span class="badge bg-secondary fw-normal ms-1">{{ ob.codigo }}</span>
    </h2>
    <small class="text-muted">Estado administrativo de la obra</small>
  </div>
  <a href="/obras/{{ ob.id_obra }}/editar" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left"></i> Ficha de obra</a>
</div>

{% if ob.estado == 'finalizada' %}
<div class="alert alert-secondary d-flex justify-content-between align-items-center">
  <span><i class="bi bi-lock-fill"></i> <strong>OBRA FINALIZADA.</strong> Diarios, mensuales y documentación en solo lectura.</span>
  <form method="post" action="/obras/{{ ob.id_obra }}/reactivar"
        onsubmit="return confirm('¿Reactivar la obra {{ ob.nombre }}? Los mensuales seguirán cerrados hasta reabrirlos.')">
    <button class="btn btn-outline-warning btn-sm"><i class="bi bi-unlock"></i> Reabrir obra</button>
  </form>
</div>
{% else %}
<div class="alert alert-success d-flex justify-content-between align-items-center flex-wrap gap-2">
  <span><i class="bi bi-unlock-fill"></i> <strong>OBRA ACTIVA.</strong></span>
  {% if puede_finalizar %}
  <form method="post" action="/obras/{{ ob.id_obra }}/cerrar"
        onsubmit="return confirm('¿Finalizar la obra {{ ob.nombre }}? Se bloquearán diarios, mensuales y documentación.')">
    <button class="btn btn-warning btn-sm"><i class="bi bi-flag"></i> Finalizar obra</button>
  </form>
  {% else %}
  <span class="text-muted small">{{ abiertos|length }} mensual(es) abierto(s): ciérralos para poder finalizar la obra.</span>
  {% endif %}
</div>
{% endif %}

<div class="sec">Mensuales por empresa</div>
<div class="card mb-4"><div class="card-body p-0">
<table class="table table-sm table-hover mb-0">
  <thead><tr><th>Mes</th><th>Empresa</th><th>Estado</th><th class="text-end">Acciones</th></tr></thead>
  <tbody>
  {% for m in mensuales %}
  <tr>
    <td class="font-monospace">{{ m.mes }}</td>
    <td>{{ m.nom_e }}</td>
    <td><span class="badge badge-{{ m.estado }}">{{ m.estado }}</span></td>
    <td class="text-end">
      <a href="/mensual/{{ m.id_mensual }}" class="btn btn-sm btn-outline-secondary py-0"><i class="bi bi-eye"></i></a>
      {% if m.estado=='abierto' %}
      <form method="post" action="/mensual/{{ m.id_mensual }}/cerrar" class="d-inline"
            onsubmit="return confirm('¿Cerrar este mes?')">
        <button class="btn btn-sm btn-outline-warning py-0" {{ 'disabled' if ob.estado=='finalizada' }}><i class="bi bi-lock"></i></button>
      </form>
      {% else %}
      <form method="post" action="/mensual/{{ m.id_mensual }}/reabrir" class="d-inline"
            onsubmit="return confirm('¿Reabrir este mes? Se perderá el snapshot actual.')">
        <button class="btn btn-sm btn-outline-warning py-0" {{ 'disabled' if ob.estado=='finalizada' }}><i class="bi bi-unlock"></i></button>
      </form>
      {% endif %}
    </td>
  </tr>
  {% else %}
  <tr><td colspan="4" class="text-center py-3 text-muted">Sin mensuales para esta obra.</td></tr>
  {% endfor %}
  </tbody>
</table></div></div>

<div class="sec"><i class="bi bi-journal-text"></i> Actividad administrativa</div>
<div class="card"><div class="card-body p-0">
<table class="table table-sm mb-0" style="font-size:.78rem">
  <thead><tr><th>Fecha</th><th>Evento</th><th>Detalle</th></tr></thead>
  <tbody>
  {% for l in logs %}
  <tr>
    <td class="text-muted font-monospace">{{ l.fecha }}</td>
    <td><span class="badge bg-secondary">{{ l.tipo_evento }}</span></td>
    <td class="small">
      {% for k,v in l.detalle_obj.items() %}
        {% if k not in ['obra_id'] %}<span class="text-muted">{{ k }}:</span> {{ v }}&nbsp; {% endif %}
      {% endfor %}
    </td>
  </tr>
  {% else %}
  <tr><td colspan="3" class="text-center py-3 text-muted">Sin actividad registrada todavía.</td></tr>
  {% endfor %}
  </tbody>
</table></div></div>
{% endblock %}"""

# ======================= DOCUMENTACIÓN POR OBRA/PARTIDA (3.3, 4.6) ============
@app.route('/obra/<int:id_obra>/documentacion')
def obra_documentacion(id_obra):
    db = get_db()
    obra = db.execute('SELECT * FROM obra WHERE id_obra=?', [id_obra]).fetchone()
    if not obra: flash('Obra no encontrada.', 'error'); return redirect(url_for('obras'))

    partidas = db.execute('SELECT * FROM partida_obra WHERE id_obra=? ORDER BY codigo', [id_obra]).fetchall()
    todas_carpetas  = db.execute('SELECT * FROM carpeta_obra WHERE id_obra=? AND archivada=0 ORDER BY nombre', [id_obra]).fetchall()
    carpetas_archivadas = db.execute('SELECT * FROM carpeta_obra WHERE id_obra=? AND archivada=1 ORDER BY ruta_relativa', [id_obra]).fetchall()
    todos_archivos  = db.execute("""SELECT a.* FROM archivo_obra a JOIN carpeta_obra c ON a.id_carpeta=c.id_carpeta
                                    WHERE c.id_obra=? ORDER BY a.nombre""", [id_obra]).fetchall()

    archivos_por_carpeta = {}
    for a in todos_archivos:
        archivos_por_carpeta.setdefault(a['id_carpeta'], []).append(a)

    subcarpetas_por_padre = {}
    raiz_por_partida = {}
    for c in todas_carpetas:
        if c['id_padre']:
            subcarpetas_por_padre.setdefault(c['id_padre'], []).append(c)
        else:
            raiz_por_partida.setdefault(c['id_partida'], []).append(c)

    grupos = [{'partida': p, 'carpetas': raiz_por_partida.get(p['id_partida'], [])} for p in partidas]
    grupos.append({'partida': None, 'carpetas': raiz_por_partida.get(None, [])})  # documentación general de la obra

    todas_carpetas_sel = todas_carpetas  # para el <select> de "carpeta padre" al crear subcarpetas
    partida_foco = request.args.get('partida', type=int)

    return render_template_string(BASE + _DOC_TPL, obra=obra, partidas=partidas, grupos=grupos,
                                  subcarpetas_por_padre=subcarpetas_por_padre,
                                  archivos_por_carpeta=archivos_por_carpeta,
                                  todas_carpetas_sel=todas_carpetas_sel, partida_foco=partida_foco,
                                  carpetas_archivadas=carpetas_archivadas)

@app.route('/obra/<int:id_obra>/documentacion/carpeta/nueva', methods=['POST'])
def doc_carpeta_nueva(id_obra):
    db = get_db()
    try:
        _chk_obra_activa(id_obra)
        nombre = request.form.get('nombre','').strip()
        if not nombre: raise ValueError('El nombre de la carpeta es obligatorio.')
        id_partida = request.form.get('id_partida') or None
        id_padre   = request.form.get('id_padre') or None
        cur = db.execute('INSERT INTO carpeta_obra(id_obra,id_partida,nombre,ruta_relativa,id_padre) VALUES(?,?,?,?,?)',
                         [id_obra, id_partida, nombre, '', id_padre])
        id_carpeta = cur.lastrowid
        ruta_rel = _ruta_carpeta_obra(id_obra, nombre, id_carpeta)
        db.execute('UPDATE carpeta_obra SET ruta_relativa=? WHERE id_carpeta=?', [ruta_rel, id_carpeta])
        os.makedirs(os.path.join(DOCS_DIR, ruta_rel), exist_ok=True)
        db.commit()
        flash(f'Carpeta "{nombre}" creada.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('obra_documentacion', id_obra=id_obra))

@app.route('/obra/<int:id_obra>/documentacion/carpeta/<int:id_carpeta>/subir', methods=['POST'])
def doc_archivo_subir(id_obra, id_carpeta):
    db = get_db()
    try:
        _chk_obra_activa(id_obra)
        carpeta = db.execute('SELECT * FROM carpeta_obra WHERE id_carpeta=? AND id_obra=?', [id_carpeta, id_obra]).fetchone()
        if not carpeta: raise ValueError('Carpeta no encontrada.')

        # Aceptamos tanto el campo nuevo "archivos" (con multiple) como el
        # antiguo "archivo" (por compatibilidad si algún formulario externo
        # todavía lo usa), y siempre procesamos una LISTA de ficheros.
        ficheros = [f for f in request.files.getlist('archivos') if f and f.filename]
        if not ficheros:
            f_legacy = request.files.get('archivo')
            if f_legacy and f_legacy.filename:
                ficheros = [f_legacy]
        if not ficheros:
            raise ValueError('Selecciona al menos un archivo.')

        destino_dir = os.path.join(DOCS_DIR, carpeta['ruta_relativa'])
        os.makedirs(destino_dir, exist_ok=True)
        notas = request.form.get('notas','').strip()
        subidos, fallidos = [], []

        for f in ficheros:
            try:
                nombre_seguro = secure_filename(f.filename) or 'archivo'
                base, ext = os.path.splitext(nombre_seguro)
                destino_abs, i = os.path.join(destino_dir, nombre_seguro), 1
                while os.path.exists(destino_abs):
                    nombre_seguro = f'{base}_{i}{ext}'
                    destino_abs = os.path.join(destino_dir, nombre_seguro)
                    i += 1
                f.save(destino_abs)
                ruta_rel = os.path.join(carpeta['ruta_relativa'], nombre_seguro)
                tipo_mime = f.mimetype or mimetypes.guess_type(nombre_seguro)[0]
                db.execute('INSERT INTO archivo_obra(id_carpeta,nombre,ruta_relativa,tipo_mime,fecha_subida,notas) VALUES(?,?,?,?,?,?)',
                          [id_carpeta, f.filename, ruta_rel, tipo_mime,
                           datetime.now().strftime('%Y-%m-%d %H:%M:%S'), notas])
                subidos.append(f.filename)
            except Exception as e:
                fallidos.append((f.filename, str(e)))
        db.commit()

        if subidos:
            if len(subidos) == 1:
                flash(f'Archivo "{subidos[0]}" subido.', 'success')
            else:
                flash(f'{len(subidos)} archivos subidos: {", ".join(subidos)}.', 'success')
        if fallidos:
            detalle = '; '.join(f'{n}: {m}' for n, m in fallidos)
            flash(f'{len(fallidos)} archivo(s) no se pudieron subir — {detalle}', 'error')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Error al subir los archivos: {e}', 'error')
    return redirect(url_for('obra_documentacion', id_obra=id_obra))

@app.route('/documentacion/archivo/<int:id_archivo>/descargar')
def doc_archivo_descargar(id_archivo):
    db = get_db()
    a = db.execute('SELECT * FROM archivo_obra WHERE id_archivo=?', [id_archivo]).fetchone()
    if not a: abort(404)
    ruta_abs = os.path.join(DOCS_DIR, a['ruta_relativa'])
    if not os.path.isfile(ruta_abs):
        flash('El archivo ya no existe en disco.', 'error')
        c = db.execute('SELECT id_obra FROM carpeta_obra WHERE id_carpeta=?', [a['id_carpeta']]).fetchone()
        return redirect(url_for('obra_documentacion', id_obra=c['id_obra']) if c else url_for('obras'))
    return send_file(ruta_abs, as_attachment=True, download_name=a['nombre'])

_DOC_TPL = r"""
{% block amae %}hi{% endblock %}{% block title %}Documentación {{ obra.nombre }}{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
  <div>
    <h2 class="h4 mb-0"><i class="bi bi-folder2-open"></i> Documentación — {{ obra.nombre }}</h2>
    <small class="text-muted">Planos, fotos y PDFs organizados por partida</small>
  </div>
  <a href="/obras/{{ obra.id_obra }}/editar" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left"></i> Ficha de obra</a>
</div>

{% if obra.estado == 'finalizada' %}
<div class="alert alert-secondary"><i class="bi bi-lock-fill"></i> Obra finalizada: documentación en solo lectura (ver/descargar).</div>
{% else %}
<div class="card mb-3"><div class="card-header">Nueva carpeta</div><div class="card-body">
<form method="post" action="/obra/{{ obra.id_obra }}/documentacion/carpeta/nueva" class="row g-2 align-items-end">
  <div class="col-md-4"><label class="form-label small mb-1">Nombre *</label>
    <input type="text" name="nombre" class="form-control form-control-sm" required></div>
  <div class="col-md-4"><label class="form-label small mb-1">Partida</label>
    <select name="id_partida" class="form-select form-select-sm">
      <option value="">— General (sin partida) —</option>
      {% for p in partidas %}<option value="{{ p.id_partida }}" {{ 'selected' if partida_foco==p.id_partida }}>{{ p.codigo }} {{ p.descripcion }}</option>{% endfor %}
    </select></div>
  <div class="col-md-3"><label class="form-label small mb-1">Dentro de <span class="text-muted">(opc.)</span></label>
    <select name="id_padre" class="form-select form-select-sm">
      <option value="">— Raíz —</option>
      {% for c in todas_carpetas_sel %}<option value="{{ c.id_carpeta }}">{{ c.nombre }}</option>{% endfor %}
    </select></div>
  <div class="col-md-1"><button class="btn btn-opl btn-sm w-100"><i class="bi bi-plus"></i></button></div>
</form>
</div></div>
{% endif %}

{% for g in grupos %}
<div class="sec {{ 'border-warning' if partida_foco and g.partida and g.partida.id_partida==partida_foco }}">
  {% if g.partida %}<i class="bi bi-bookmark"></i> {{ g.partida.codigo }} — {{ g.partida.descripcion }}
  {% else %}<i class="bi bi-archive"></i> General (sin partida asociada){% endif %}
</div>
{% if g.carpetas %}
<div class="row g-2 mb-3">
{% for c in g.carpetas %}
<div class="col-md-6">
  <div class="card h-100"><div class="card-header py-1 d-flex justify-content-between align-items-center">
    <span class="small"><i class="bi bi-folder-fill text-warning"></i> {{ c.nombre }}</span>
  </div>
  <div class="card-body py-2">
    <ul class="list-unstyled mb-2 small">
      {% for a in archivos_por_carpeta.get(c.id_carpeta, []) %}
      <li><i class="bi bi-file-earmark"></i> <a href="/documentacion/archivo/{{ a.id_archivo }}/descargar">{{ a.nombre }}</a>
        <span class="text-muted" style="font-size:.68rem">({{ a.fecha_subida }})</span></li>
      {% else %}
      <li class="text-muted">Sin archivos.</li>
      {% endfor %}
    </ul>
    {% for sc in subcarpetas_por_padre.get(c.id_carpeta, []) %}
    <div class="border-start ps-2 mb-2">
      <div class="small"><i class="bi bi-folder2"></i> {{ sc.nombre }}</div>
      <ul class="list-unstyled small mb-1">
        {% for a in archivos_por_carpeta.get(sc.id_carpeta, []) %}
        <li><i class="bi bi-file-earmark"></i> <a href="/documentacion/archivo/{{ a.id_archivo }}/descargar">{{ a.nombre }}</a></li>
        {% else %}<li class="text-muted">Sin archivos.</li>{% endfor %}
      </ul>
      {% if obra.estado != 'finalizada' %}
      <form method="post" action="/obra/{{ obra.id_obra }}/documentacion/carpeta/{{ sc.id_carpeta }}/subir" enctype="multipart/form-data" class="d-flex gap-1">
        <input type="file" name="archivos" multiple class="form-control form-control-sm" required title="Puedes seleccionar varios archivos a la vez">
        <button class="btn btn-sm btn-outline-secondary py-0" title="Subir"><i class="bi bi-upload"></i></button>
      </form>
      {% endif %}
    </div>
    {% endfor %}
    {% if obra.estado != 'finalizada' %}
    <form method="post" action="/obra/{{ obra.id_obra }}/documentacion/carpeta/{{ c.id_carpeta }}/subir" enctype="multipart/form-data" class="d-flex gap-1">
      <input type="file" name="archivos" multiple class="form-control form-control-sm" required title="Puedes seleccionar varios archivos a la vez">
      <button class="btn btn-sm btn-outline-secondary py-0" title="Subir"><i class="bi bi-upload"></i></button>
    </form>
    {% endif %}
  </div></div>
</div>
{% endfor %}
</div>
{% else %}
<p class="text-muted small mb-3">Sin carpetas todavía.</p>
{% endif %}
{% endfor %}

{% if carpetas_archivadas %}
<div class="sec text-muted"><i class="bi bi-archive"></i> Documentación archivada
  <span class="badge bg-secondary fw-normal">{{ carpetas_archivadas|length }}</span>
</div>
<p class="text-muted small">Documentación de partidas eliminadas. No se borra nunca: sigue siendo descargable.</p>
<div class="row g-2 mb-3">
{% for c in carpetas_archivadas %}
<div class="col-md-6">
  <div class="card border-secondary h-100"><div class="card-header py-1 text-muted small">
    <i class="bi bi-folder-fill"></i> {{ c.nombre }} <span class="badge bg-secondary">archivada</span>
  </div>
  <div class="card-body py-2">
    <ul class="list-unstyled mb-0 small">
      {% for a in archivos_por_carpeta.get(c.id_carpeta, []) %}
      <li><i class="bi bi-file-earmark"></i> <a href="/documentacion/archivo/{{ a.id_archivo }}/descargar">{{ a.nombre }}</a></li>
      {% else %}<li class="text-muted">Sin archivos.</li>{% endfor %}
    </ul>
  </div></div>
</div>
{% endfor %}
</div>
{% endif %}
{% endblock %}"""

_OBRA_FORM = r"""
{% block amae %}hi{% endblock %}
{% block title %}{{ 'Editar' if ob else 'Nueva' }} obra{% endblock %}
{% block content %}
<div class="row g-3">
<div class="col-md-5">
  <div class="card mb-3"><div class="card-header d-flex justify-content-between align-items-center">
    <h5 class="mb-0">{{ 'Editar' if ob else 'Nueva' }} obra</h5>
    {% if ob %}<span class="badge badge-{{ ob.estado }}">{{ ob.estado }}</span>{% endif %}
  </div>
  <div class="card-body">
  {% if ob %}
  <div class="d-flex gap-2 mb-3">
    <a href="/obras/{{ ob.id_obra }}/estado" class="btn btn-outline-warning btn-sm"><i class="bi bi-clipboard-data"></i> Estado de obra</a>
    <a href="/obra/{{ ob.id_obra }}/documentacion" class="btn btn-outline-primary btn-sm"><i class="bi bi-folder2-open"></i> Documentación</a>
  </div>
  {% endif %}
  <form method="post">
    <div class="row g-2 mb-2">
      <div class="col-4"><label class="form-label small">Código *</label>
        <input type="text" name="codigo" class="form-control form-control-sm" value="{{ ob.codigo if ob else '' }}" required></div>
      <div class="col-8"><label class="form-label small">Nombre *</label>
        <input type="text" name="nombre" class="form-control form-control-sm" value="{{ ob.nombre if ob else '' }}" required autofocus></div>
    </div>
    {% if ob %}
    <div class="mb-3"><label class="form-label small">Meta de horas/día <span class="text-muted">(opc.)</span></label>
      <input type="number" name="meta_horas_dia" class="form-control form-control-sm" step="0.25" min="0.25"
             value="{{ ob.meta_horas_dia if ob.meta_horas_dia is not none else '' }}"
             placeholder="8h por defecto" {{ 'readonly' if ob.estado=='finalizada' }}>
      {% if ob.estado=='finalizada' %}<div class="form-text text-warning">Obra finalizada: solo lectura.</div>{% endif %}
    </div>
    <div class="alert alert-secondary small py-2">
      <i class="bi bi-info-circle"></i> El estado (activa/finalizada) se gestiona desde
      <a href="/obras/{{ ob.id_obra }}/estado">Estado de obra</a>, donde se comprueban los mensuales abiertos.
    </div>
    {% endif %}
    <div class="d-flex gap-2">
      <button type="submit" class="btn btn-opl btn-sm">Guardar</button>
      <a href="/obras/" class="btn btn-secondary btn-sm">Cancelar</a>
    </div>
  </form></div></div>

  {% if ob %}
  <!-- Empresas en obra -->
  <div class="card mb-3"><div class="card-header">Empresas participantes</div><div class="card-body p-0">
    <table class="table table-sm mb-0">
      <tbody>
      {% for e in oes %}
      <tr><td>{{ e.nombre }}</td><td class="text-end">
        <form method="post" action="/obras/{{ ob.id_obra }}/rem-empresa/{{ e.id_oe }}" class="d-inline">
          <button class="btn btn-sm btn-outline-danger py-0"><i class="bi bi-x"></i></button>
        </form></td></tr>
      {% else %}<tr><td class="text-muted text-center">Sin empresas</td></tr>{% endfor %}
      </tbody>
    </table>
    {% if emps_disp %}
    <form method="post" action="/obras/{{ ob.id_obra }}/add-empresa" class="p-2 d-flex gap-2">
      <select name="id_empresa" class="form-select form-select-sm">
        {% for e in emps_disp %}<option value="{{ e.id_empresa }}">{{ e.nombre }}</option>{% endfor %}
      </select>
      <button class="btn btn-opl btn-sm"><i class="bi bi-plus"></i></button>
    </form>
    {% endif %}
  </div></div>

  <!-- Partidas -->
  <div class="card"><div class="card-header">Partidas / fases</div><div class="card-body p-0">
    <table class="table table-sm mb-0">
      <tbody>
      {% for p in parts %}
      <tr>
        <td class="font-monospace">{{ p.codigo }}</td>
        <td class="text-muted small">{{ p.descripcion }}</td>
        <td class="text-end">
          <form method="post" action="/obras/{{ ob.id_obra }}/rem-partida/{{ p.id_partida }}" class="d-inline">
            <button class="btn btn-sm btn-outline-danger py-0"><i class="bi bi-x"></i></button>
          </form>
        </td>
      </tr>
      {% else %}<tr><td colspan="3" class="text-muted text-center">Sin partidas</td></tr>{% endfor %}
      </tbody>
    </table>
    <form method="post" action="/obras/{{ ob.id_obra }}/add-partida" class="p-2 d-flex gap-2">
      <input type="text" name="codigo" class="form-control form-control-sm" placeholder="1.1" style="width:75px">
      <input type="text" name="descripcion" class="form-control form-control-sm" placeholder="Descripción">
      <button class="btn btn-opl btn-sm"><i class="bi bi-plus"></i></button>
    </form>
  </div></div>
  {% endif %}
</div></div>
{% endblock %}"""

# -- DIARIO --
@app.route('/diario/')
def diario_sel():
    obras = get_db().execute("SELECT * FROM obra WHERE estado='activa' ORDER BY nombre").fetchall()
    return render_template_string(BASE + r"""
{% block ad %}hi{% endblock %}{% block title %}Diario{% endblock %}
{% block content %}
<h2 class="h4 mb-3"><i class="bi bi-calendar-day"></i> Parte diario</h2>
<div class="row g-3">
<div class="col-md-4">
  <div class="card"><div class="card-body">
    <form action="/diario/ir" method="get">
      <div class="mb-3"><label class="form-label">Obra</label>
        <select name="id_obra" class="form-select" required>
          <option value="">— Selecciona —</option>
          {% for o in obras %}<option value="{{ o.id_obra }}">{{ o.codigo }} — {{ o.nombre }}</option>{% endfor %}
        </select></div>
      <div class="mb-3"><label class="form-label">Fecha</label>
        <input type="date" name="fecha" class="form-control" value="{{ hoy }}" required></div>
      <button type="submit" class="btn btn-opl w-100">Abrir parte</button>
    </form>
  </div></div>
</div>
<div class="col-md-8">
  <div class="sec">Acceso rápido — hoy ({{ hoy }})</div>
  <div class="row g-2">
    {% for o in obras %}
    <div class="col-6 col-xl-4">
      <a href="/diario/{{ o.id_obra }}/{{ hoy }}" class="btn btn-outline-secondary btn-sm w-100 text-start py-2">
        <strong>{{ o.nombre }}</strong><br><small class="text-muted">{{ o.codigo }}</small>
      </a>
    </div>
    {% endfor %}
  </div>
</div></div>
{% endblock %}
""", obras=obras)

@app.route('/diario/ir')
def diario_ir():
    id_obra = request.args.get('id_obra', type=int)
    fecha   = request.args.get('fecha', fs(date_type.today()))
    if not id_obra: return redirect(url_for('diario_sel'))
    return redirect(url_for('diario_ver', id_obra=id_obra, fecha_raw=fecha))

@app.route('/diario/<int:id_obra>/<fecha_raw>')
def diario_ver(id_obra, fecha_raw):
    db = get_db()
    try: fecha = fs(nf(fecha_raw))
    except: flash('Fecha inválida.', 'error'); return redirect(url_for('diario_sel'))

    obra = db.execute('SELECT * FROM obra WHERE id_obra=?', [id_obra]).fetchone()
    if not obra: flash('Obra no encontrada.', 'error'); return redirect(url_for('diario_sel'))

    d = db.execute('SELECT * FROM diario WHERE id_obra=? AND fecha=?', [id_obra, fecha]).fetchone()
    if not d:
        if obra['estado'] == 'finalizada':
            flash(f'La obra "{obra["nombre"]}" está finalizada: no existe parte para {fecha} y no se pueden crear nuevos.', 'error')
            return redirect(url_for('obra_estado', id_obra=id_obra))
        db.execute('INSERT INTO diario(id_obra,fecha) VALUES(?,?)', [id_obra, fecha]); db.commit()
        d = db.execute('SELECT * FROM diario WHERE id_obra=? AND fecha=?', [id_obra, fecha]).fetchone()

    lineas = db.execute("""
        SELECT dl.*, p.nombre nom_p, p.apellido1 ap1, p.apellido2 ap2, p.dni,
               e.nombre nom_e, r.codigo cod_r, pa.codigo cod_pa, pa.descripcion desc_pa
        FROM diario_linea dl
        JOIN persona p  ON dl.id_persona = p.id_persona
        JOIN empresa e  ON dl.id_empresa = e.id_empresa
        LEFT JOIN rango r        ON dl.id_rango   = r.id_rango
        LEFT JOIN partida_obra pa ON dl.id_partida = pa.id_partida
        WHERE dl.id_diario=?
        ORDER BY e.nombre, p.apellido1, p.nombre""", [d['id_diario']]).fetchall()

    emps_obra = db.execute("""SELECT e.* FROM empresa e
        JOIN obra_empresa oe ON e.id_empresa=oe.id_empresa
        WHERE oe.id_obra=? ORDER BY e.nombre""", [id_obra]).fetchall()

    pers_x_emp = {}
    for e in emps_obra:
        pers_x_emp[e['id_empresa']] = [
            dict(r) for r in db.execute(
                "SELECT * FROM persona WHERE id_empresa=? AND estado='activa' ORDER BY apellido1,nombre",
                [e['id_empresa']]).fetchall()
        ]

    rangos   = db.execute("SELECT * FROM rango ORDER BY codigo").fetchall()
    partidas = db.execute("SELECT * FROM partida_obra WHERE id_obra=? ORDER BY codigo", [id_obra]).fetchall()
    ant      = db.execute("SELECT fecha FROM diario WHERE id_obra=? AND fecha<? ORDER BY fecha DESC LIMIT 1",
                          [id_obra, fecha]).fetchone()
    total    = db.execute("SELECT COALESCE(SUM(horas),0) t FROM diario_linea WHERE id_diario=?", [d['id_diario']]).fetchone()['t']

    METEO = [('soleado','soleado'),('nublado','nublado'),('lluvioso','lluvioso'),
             ('tormentoso','tormentoso'),('nevando','nevando'),('ventoso','ventoso'),('niebla','niebla')]
    m_ico = dict(METEO)

    return render_template_string(BASE + r"""
{% block ad %}hi{% endblock %}
{% block title %}Parte {{ fecha }}{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
  <div>
    <h2 class="h4 mb-0"><i class="bi bi-calendar-day"></i> {{ obra.nombre }}
      <span class="badge bg-secondary fw-normal ms-1">{{ obra.codigo }}</span>
    </h2>
    <small class="text-muted">{{ fecha }}</small>
  </div>
  <div class="d-flex gap-2">
    <a href="/diario/" class="btn btn-sm btn-outline-secondary"><i class="bi bi-calendar3"></i></a>
    {% if obra.estado != 'finalizada' %}
    <a href="/diario/{{ d.id_diario }}/asignacion-masiva" class="btn btn-sm btn-outline-success">
      <i class="bi bi-people-fill"></i> Asignación masiva
    </a>
    {% if ant %}
    <form method="post" action="/diario/{{ d.id_diario }}/arrastrar"
          onsubmit="return confirm('¿Arrastrar personas de {{ ant.fecha }}? Las horas se pondrán a 0.')">
      <button class="btn btn-sm btn-outline-info">
        <i class="bi bi-arrow-repeat"></i> Arrastrar de {{ ant.fecha }}
      </button>
    </form>
    {% endif %}
    {% endif %}
  </div>
</div>

{% if obra.estado == 'finalizada' %}
<div class="alert alert-secondary"><i class="bi bi-lock-fill"></i> Obra finalizada: este parte es de solo lectura.</div>
{% endif %}

<!-- METEO -->
<div class="card mb-3">
  <div class="card-header d-flex justify-content-between align-items-center py-2">
    <span>
      <i class="bi bi-cloud-sun"></i>
      <strong class="ms-1">{{ m_ico.get(d.meteo_estado,'?') }} {{ d.meteo_estado|capitalize }}</strong>
      {% if d.meteo_temp_c %}<span class="text-muted ms-2">{{ d.meteo_temp_c }}°C</span>{% endif %}
      {% if d.meteo_detalle %}<span class="text-muted ms-2">— {{ d.meteo_detalle }}</span>{% endif %}
    </span>
    <button class="btn btn-sm btn-outline-secondary py-0" type="button"
            data-bs-toggle="collapse" data-bs-target="#fmeteo" {{ 'style=display:none' if obra.estado=='finalizada' }}>
      <i class="bi bi-pencil"></i>
    </button>
  </div>
  {% if obra.estado != 'finalizada' %}
  <div class="collapse" id="fmeteo"><div class="card-body py-2">
    <form method="post" action="/diario/{{ d.id_diario }}/meteo" class="row g-2 align-items-end">
      <div class="col-auto"><label class="form-label small mb-1">Estado</label>
        <select name="meteo_estado" class="form-select form-select-sm">
          {% for k,v in METEO %}
          <option value="{{ k }}" {{ 'selected' if d.meteo_estado==k }}>{{ v }} {{ k|capitalize }}</option>
          {% endfor %}
        </select></div>
      <div class="col"><label class="form-label small mb-1">Detalle</label>
        <input type="text" name="meteo_detalle" class="form-control form-control-sm" value="{{ d.meteo_detalle }}" placeholder="Notas..."></div>
      <div class="col-auto"><label class="form-label small mb-1">°C</label>
        <input type="number" name="meteo_temp_c" class="form-control form-control-sm" value="{{ d.meteo_temp_c or '' }}" step="0.5" style="width:75px"></div>
      <div class="col-auto"><button class="btn btn-opl btn-sm">Guardar</button></div>
    </form>
  </div></div>
  {% endif %}
</div>

<!-- TABLA LINEAS -->
<div class="d-flex align-items-center mb-2 gap-3">
  <div class="sec mb-0">Personal registrado
    <span class="badge bg-secondary ms-1">{{ lineas|length }}</span>
    <span class="ms-2 text-muted small fw-normal">Total: <strong>{{ hhmm(total) }}</strong></span>
  </div>
</div>

{% if lineas %}
<div class="card mb-3"><div class="card-body p-0">
<table class="table table-sm table-hover mb-0">
  <thead><tr><th>Persona</th><th>Empresa</th><th>Rango</th><th>Partida</th><th>Asunto</th><th class="hth">Horas</th><th class="hth"></th></tr></thead>
  <tbody>
  {% for l in lineas %}
  <tr>
    <td>{{ l.ap1 }} {{ l.ap2 }}, {{ l.nom_p }}<br>
      <small class="text-muted font-monospace">{{ l.dni }}</small></td>
    <td class="small">{{ l.nom_e }}</td>
    <td><span class="badge bg-secondary" style="font-size:.65rem">{{ l.cod_r or '—' }}</span></td>
    <td class="font-monospace small">
      {{ l.cod_pa or '—' }}
      {% if l.id_partida %}
      <a href="/obra/{{ obra.id_obra }}/documentacion?partida={{ l.id_partida }}" class="text-muted" title="Ver documentación de la partida">
        <i class="bi bi-folder2-open"></i></a>
      {% endif %}
    </td>
    <td class="small text-muted">{{ l.asunto or '—' }}</td>
    <td class="htd">
      {% if obra.estado != 'finalizada' %}
      <button class="btn btn-link btn-sm p-0 text-light fw-bold"
              data-bs-toggle="collapse" data-bs-target="#ed{{ l.id_dl }}">
        {{ hhmm(l.horas) }}
      </button>
      {% else %}
      <span class="fw-bold">{{ hhmm(l.horas) }}</span>
      {% endif %}
    </td>
    <td class="text-center">
      {% if obra.estado != 'finalizada' %}
      <form method="post" action="/diario/linea/{{ l.id_dl }}/eliminar" class="d-inline"
            onsubmit="return confirm('¿Eliminar línea?')">
        <button class="btn btn-sm btn-outline-danger py-0 px-1"><i class="bi bi-x"></i></button>
      </form>
      {% endif %}
    </td>
  </tr>
  {% if obra.estado != 'finalizada' %}
  <tr class="collapse" id="ed{{ l.id_dl }}">
    <td colspan="7" class="bg-dark p-2">
      <form method="post" action="/diario/linea/{{ l.id_dl }}/editar" class="row g-2 align-items-end">
        <div class="col-auto"><label class="form-label small mb-1">Horas</label>
          <input type="number" name="horas" class="form-control form-control-sm" value="{{ l.horas }}"
                 step="0.25" min="0" max="24" style="width:80px"></div>
        <div class="col"><label class="form-label small mb-1">Asunto</label>
          <input type="text" name="asunto" class="form-control form-control-sm" value="{{ l.asunto }}"></div>
        <div class="col-auto"><label class="form-label small mb-1">Rango</label>
          <select name="id_rango" class="form-select form-select-sm">
            <option value="">—</option>
            {% for r in rangos %}<option value="{{ r.id_rango }}" {{ 'selected' if r.id_rango==l.id_rango }}>{{ r.codigo }}</option>{% endfor %}
          </select></div>
        <div class="col-auto"><label class="form-label small mb-1">Partida</label>
          <select name="id_partida" class="form-select form-select-sm">
            <option value="">—</option>
            {% for p in partidas %}<option value="{{ p.id_partida }}" {{ 'selected' if p.id_partida==l.id_partida }}>{{ p.codigo }}</option>{% endfor %}
          </select></div>
        <div class="col-auto"><button class="btn btn-opl btn-sm">Actualizar</button></div>
      </form>
    </td>
  </tr>
  {% endif %}
  {% endfor %}
  </tbody>
</table></div></div>
{% else %}
<div class="alert alert-secondary">Sin personal registrado hoy.</div>
{% endif %}

{% if obra.estado != 'finalizada' %}
<!-- NUEVA LÍNEA -->
<div class="card"><div class="card-header"><i class="bi bi-plus"></i> Añadir persona</div>
<div class="card-body">
<form method="post" action="/diario/{{ d.id_diario }}/linea/nueva">
  <div class="row g-2 align-items-end">
    <div class="col-md-3"><label class="form-label small mb-1">Empresa *</label>
      <select name="id_empresa" id="sel-emp" class="form-select form-select-sm" required>
        <option value="">— Empresa —</option>
        {% for e in emps_obra %}<option value="{{ e.id_empresa }}">{{ e.nombre }}</option>{% endfor %}
      </select></div>
    <div class="col-md-3"><label class="form-label small mb-1">Persona *</label>
      <select name="id_persona" id="sel-per" class="form-select form-select-sm" required>
        <option value="">— Persona —</option>
      </select></div>
    <div class="col-md-1"><label class="form-label small mb-1">Horas</label>
      <input type="number" name="horas" class="form-control form-control-sm" value="8" step="0.25" min="0" max="24" required></div>
    <div class="col-md-2"><label class="form-label small mb-1">Rango</label>
      <select name="id_rango" class="form-select form-select-sm">
        <option value="">— Auto —</option>
        {% for r in rangos %}<option value="{{ r.id_rango }}">{{ r.codigo }}</option>{% endfor %}
      </select></div>
    <div class="col-md-2"><label class="form-label small mb-1">Partida</label>
      <select name="id_partida" class="form-select form-select-sm">
        <option value="">—</option>
        {% for p in partidas %}<option value="{{ p.id_partida }}">{{ p.codigo }} {{ p.descripcion }}</option>{% endfor %}
      </select></div>
    <div class="col-12"><label class="form-label small mb-1">Asunto</label>
      <input type="text" name="asunto" class="form-control form-control-sm" placeholder="Trabajos realizados..."></div>
    <div class="col-auto"><button type="submit" class="btn btn-opl btn-sm"><i class="bi bi-plus"></i> Añadir</button></div>
  </div>
</form>
</div></div>
{% endif %}
{% endblock %}
{% block scripts %}
<script>
const pxe = {{ pers_x_emp | tojson }};
document.getElementById('sel-emp').addEventListener('change', function(){
  const s = document.getElementById('sel-per');
  s.innerHTML = '<option value="">— Persona —</option>';
  (pxe[this.value]||[]).forEach(p => {
    const o = document.createElement('option');
    o.value = p.id_persona;
    o.textContent = p.apellido1+' '+(p.apellido2||'')+', '+p.nombre+' ('+p.dni+')';
    s.appendChild(o);
  });
});
</script>
{% endblock %}
""", obra=obra, d=d, lineas=lineas, fecha=fecha,
                                  emps_obra=emps_obra, pers_x_emp=pers_x_emp,
                                  rangos=rangos, partidas=partidas, ant=ant,
                                  total=total, hhmm=hhmm, m_ico=m_ico, METEO=METEO)

@app.route('/diario/<int:id_d>/linea/nueva', methods=['POST'])
def diario_linea_nueva(id_d):
    db = get_db()
    d = db.execute('SELECT * FROM diario WHERE id_diario=?', [id_d]).fetchone()
    if not d: flash('Diario no encontrado.', 'error'); return redirect(url_for('diario_sel'))
    try:
        _chk_obra_activa(d['id_obra'])
        id_emp = int(request.form['id_empresa'])
        id_per = int(request.form['id_persona'])
        horas  = float(request.form.get('horas', 0))
        asunto = request.form.get('asunto','').strip()
        id_r   = request.form.get('id_rango') or get_rango_activo(id_per, d['fecha'])
        id_pa  = request.form.get('id_partida') or None
        chk_mes_cerrado(d['id_obra'], id_emp, d['fecha'])
        chk_horas(id_per, d['fecha'], horas)
        db.execute('INSERT INTO diario_linea(id_diario,id_empresa,id_persona,id_rango,id_partida,asunto,horas) VALUES(?,?,?,?,?,?,?)',
                   [id_d, id_emp, id_per, id_r, id_pa, asunto, horas])
        db.commit(); flash('Línea añadida.', 'success')
    except ValueError as e: flash(str(e), 'error')
    except Exception as e:   flash(f'Error: {e}', 'error')
    return redirect(url_for('diario_ver', id_obra=d['id_obra'], fecha_raw=fs(d['fecha'])))

@app.route('/diario/linea/<int:id_dl>/editar', methods=['POST'])
def diario_linea_editar(id_dl):
    db = get_db()
    dl = db.execute('SELECT dl.*,d.fecha,d.id_obra FROM diario_linea dl JOIN diario d ON dl.id_diario=d.id_diario WHERE dl.id_dl=?', [id_dl]).fetchone()
    if dl:
        try:
            _chk_obra_activa(dl['id_obra'])
            h  = float(request.form.get('horas', dl['horas']))
            as_= request.form.get('asunto', dl['asunto']).strip()
            ir = request.form.get('id_rango')   or dl['id_rango']
            ip = request.form.get('id_partida') or dl['id_partida']
            chk_mes_cerrado(dl['id_obra'], dl['id_empresa'], dl['fecha'])
            chk_horas(dl['id_persona'], dl['fecha'], h, excl=id_dl)
            db.execute('UPDATE diario_linea SET horas=?,asunto=?,id_rango=?,id_partida=? WHERE id_dl=?',
                       [h, as_, ir, ip, id_dl]); db.commit()
            flash('Línea actualizada.', 'success')
        except ValueError as e: flash(str(e), 'error')
        except Exception as e:   flash(f'Error: {e}', 'error')
    return redirect(url_for('diario_ver', id_obra=dl['id_obra'], fecha_raw=fs(dl['fecha'])))

@app.route('/diario/linea/<int:id_dl>/eliminar', methods=['POST'])
def diario_linea_eliminar(id_dl):
    db = get_db()
    dl = db.execute('SELECT dl.*,d.fecha,d.id_obra FROM diario_linea dl JOIN diario d ON dl.id_diario=d.id_diario WHERE dl.id_dl=?', [id_dl]).fetchone()
    if dl:
        try:
            _chk_obra_activa(dl['id_obra'])
            chk_mes_cerrado(dl['id_obra'], dl['id_empresa'], dl['fecha'])
            db.execute('DELETE FROM diario_linea WHERE id_dl=?', [id_dl]); db.commit()
            flash('Línea eliminada.', 'success')
        except ValueError as e: flash(str(e), 'error')
    return redirect(url_for('diario_ver', id_obra=dl['id_obra'], fecha_raw=fs(dl['fecha'])))

@app.route('/diario/<int:id_d>/meteo', methods=['POST'])
def diario_meteo(id_d):
    db = get_db()
    d  = db.execute('SELECT * FROM diario WHERE id_diario=?', [id_d]).fetchone()
    try:
        _chk_obra_activa(d['id_obra'])
        t  = request.form.get('meteo_temp_c','').strip()
        db.execute('UPDATE diario SET meteo_estado=?,meteo_detalle=?,meteo_temp_c=? WHERE id_diario=?',
                   [request.form.get('meteo_estado','soleado'),
                    request.form.get('meteo_detalle','').strip(),
                    float(t) if t else None, id_d]); db.commit()
        flash('Meteorología actualizada.', 'success')
    except ValueError as e: flash(str(e), 'error')
    return redirect(url_for('diario_ver', id_obra=d['id_obra'], fecha_raw=fs(d['fecha'])))

@app.route('/diario/<int:id_d>/arrastrar', methods=['POST'])
def diario_arrastrar(id_d):
    db = get_db()
    d  = db.execute('SELECT * FROM diario WHERE id_diario=?', [id_d]).fetchone()
    if not d: return redirect(url_for('diario_sel'))
    try:
        _chk_obra_activa(d['id_obra'])
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('diario_ver', id_obra=d['id_obra'], fecha_raw=fs(d['fecha'])))
    ant = db.execute("SELECT id_diario FROM diario WHERE id_obra=? AND fecha<? ORDER BY fecha DESC LIMIT 1",
                     [d['id_obra'], d['fecha']]).fetchone()
    if not ant:
        flash('No hay parte anterior.', 'warning')
        return redirect(url_for('diario_ver', id_obra=d['id_obra'], fecha_raw=fs(d['fecha'])))
    lineas = db.execute('SELECT * FROM diario_linea WHERE id_diario=?', [ant['id_diario']]).fetchall()
    ok = 0
    for l in lineas:
        if db.execute('SELECT 1 FROM diario_linea WHERE id_diario=? AND id_persona=? AND id_empresa=?',
                      [id_d, l['id_persona'], l['id_empresa']]).fetchone():
            continue
        try:
            chk_mes_cerrado(d['id_obra'], l['id_empresa'], d['fecha'])
            ir = get_rango_activo(l['id_persona'], d['fecha'])
            db.execute('INSERT INTO diario_linea(id_diario,id_empresa,id_persona,id_rango,id_partida,asunto,horas) VALUES(?,?,?,?,?,?,0)',
                       [id_d, l['id_empresa'], l['id_persona'], ir, l['id_partida'], l['asunto']])
            ok += 1
        except ValueError as e: flash(str(e), 'error')
    db.commit()
    if ok: flash(f'{ok} línea(s) arrastradas. Revisa y corrige las horas (están a 0).', 'info')
    else:  flash('Sin líneas nuevas para arrastrar.', 'warning')
    return redirect(url_for('diario_ver', id_obra=d['id_obra'], fecha_raw=fs(d['fecha'])))

# -- ASIGNACIÓN MASIVA (4.3) --
@app.route('/diario/<int:id_diario>/asignacion-masiva', methods=['GET','POST'])
def diario_asignacion_masiva(id_diario):
    db = get_db()
    d = db.execute('SELECT * FROM diario WHERE id_diario=?', [id_diario]).fetchone()
    if not d: flash('Diario no encontrado.', 'error'); return redirect(url_for('diario_sel'))
    obra = db.execute('SELECT * FROM obra WHERE id_obra=?', [d['id_obra']]).fetchone()
    try:
        _chk_obra_activa(d['id_obra'])
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('diario_ver', id_obra=d['id_obra'], fecha_raw=fs(d['fecha'])))

    emps_obra = db.execute("""SELECT e.* FROM empresa e JOIN obra_empresa oe ON e.id_empresa=oe.id_empresa
                              WHERE oe.id_obra=? ORDER BY e.nombre""", [d['id_obra']]).fetchall()
    partidas = db.execute("SELECT * FROM partida_obra WHERE id_obra=? ORDER BY codigo", [d['id_obra']]).fetchall()
    pers_x_emp = {}
    for e in emps_obra:
        pers_x_emp[e['id_empresa']] = [
            dict(r) for r in db.execute(
                "SELECT * FROM persona WHERE id_empresa=? AND estado='activa' ORDER BY apellido1,nombre",
                [e['id_empresa']]).fetchall()
        ]

    if request.method == 'POST':
        id_emp = request.form.get('id_empresa', type=int)
        try:
            horas = float(request.form.get('horas', 0))
        except ValueError:
            horas = 0
        id_pa  = request.form.get('id_partida') or None
        asunto = request.form.get('asunto','').strip()
        ids_p  = request.form.getlist('personas', type=int)

        if not id_emp or not ids_p:
            flash('Selecciona una empresa y al menos una persona.', 'error')
            return redirect(url_for('diario_asignacion_masiva', id_diario=id_diario))

        # Defensa en profundidad: no confiamos solo en que el JS del navegador
        # haya deshabilitado los checkboxes de otras empresas. Si llega algún
        # id de persona que no pertenece a la empresa seleccionada, lo
        # ignoramos en vez de insertar una línea inconsistente.
        ids_validas = {p['id_persona'] for p in pers_x_emp.get(id_emp, [])}
        ids_ignoradas = [i for i in ids_p if i not in ids_validas]
        ids_p = [i for i in ids_p if i in ids_validas]
        if ids_ignoradas:
            flash(f'{len(ids_ignoradas)} selección(es) ignoradas por no pertenecer a la empresa elegida '
                 f'(revisa si cambiaste de empresa después de marcar personas).', 'warning')
        if not ids_p:
            flash('Ninguna de las personas seleccionadas pertenece a la empresa elegida.', 'error')
            return redirect(url_for('diario_asignacion_masiva', id_diario=id_diario))

        creadas, bloqueadas = [], []
        for id_per in ids_p:
            per = db.execute('SELECT nombre,apellido1 FROM persona WHERE id_persona=?', [id_per]).fetchone()
            nom = f"{per['apellido1']}, {per['nombre']}" if per else f"persona #{id_per}"
            try:
                if db.execute('SELECT 1 FROM diario_linea WHERE id_diario=? AND id_persona=? AND id_empresa=?',
                              [id_diario, id_per, id_emp]).fetchone():
                    bloqueadas.append((nom, 'ya tiene una línea en este parte para esta empresa.'))
                    continue
                chk_mes_cerrado(d['id_obra'], id_emp, d['fecha'])
                chk_horas(id_per, d['fecha'], horas)
                id_r = get_rango_activo(id_per, d['fecha'])
                db.execute('''INSERT INTO diario_linea(id_diario,id_empresa,id_persona,id_rango,id_partida,asunto,horas)
                              VALUES(?,?,?,?,?,?,?)''', [id_diario, id_emp, id_per, id_r, id_pa, asunto, horas])
                creadas.append(nom)
                meta, origen = get_meta_efectiva(id_per, id_emp, d['id_obra'])
                if horas < meta:
                    flash(f'{nom}: {hhmm(horas)} asignadas, por debajo de su meta efectiva de {hhmm(meta)} (origen: {origen}).', 'warning')
            except ValueError as e:
                bloqueadas.append((nom, str(e)))
        db.commit()
        if creadas:
            flash(f"{len(creadas)} línea(s) creadas para: {', '.join(creadas)}.", 'success')
        if bloqueadas:
            detalle = '; '.join(f'{n}: {m}' for n, m in bloqueadas)
            flash(f'{len(bloqueadas)} línea(s) no creadas — {detalle}', 'warning')
        return redirect(url_for('diario_ver', id_obra=d['id_obra'], fecha_raw=fs(d['fecha'])))

    return render_template_string(BASE + r"""
{% block ad %}hi{% endblock %}{% block title %}Asignación masiva{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h2 class="h4 mb-0"><i class="bi bi-people-fill"></i> Asignación masiva — {{ obra.nombre }} <small class="text-muted">{{ d.fecha }}</small></h2>
  <a href="/diario/{{ obra.id_obra }}/{{ d.fecha }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-arrow-left"></i> Volver al parte</a>
</div>
<div class="alert alert-info small"><i class="bi bi-info-circle"></i>
  Asigna la misma jornada (horas, partida, asunto) a varias personas de una misma empresa de una sola vez.
  Se valida el mes cerrado y el límite de horas/día para cada persona individualmente; las que no cumplan quedarán bloqueadas
  y el resto se crearán con normalidad.</div>
{% if not emps_obra %}
<div class="alert alert-warning">Esta obra no tiene empresas vinculadas todavía. Añade alguna desde la ficha de obra antes de usar la asignación masiva.</div>
{% endif %}
<div class="card"><div class="card-body">
<form method="post">
  <div class="row g-2 align-items-end mb-3">
    <div class="col-md-3"><label class="form-label small mb-1">Empresa *</label>
      <select name="id_empresa" id="am-emp" class="form-select form-select-sm" required {{ 'disabled' if not emps_obra }}>
        <option value="">— Empresa —</option>
        {% for e in emps_obra %}<option value="{{ e.id_empresa }}">{{ e.nombre }}</option>{% endfor %}
      </select></div>
    <div class="col-md-2"><label class="form-label small mb-1">Horas comunes *</label>
      <input type="number" name="horas" class="form-control form-control-sm" value="8" step="0.25" min="0" max="24" required></div>
    <div class="col-md-3"><label class="form-label small mb-1">Partida común</label>
      <select name="id_partida" class="form-select form-select-sm">
        <option value="">—</option>
        {% for p in partidas %}<option value="{{ p.id_partida }}">{{ p.codigo }} {{ p.descripcion }}</option>{% endfor %}
      </select></div>
    <div class="col-md-4"><label class="form-label small mb-1">Asunto común</label>
      <input type="text" name="asunto" class="form-control form-control-sm" placeholder="Trabajos realizados..."></div>
  </div>

  <div class="d-flex justify-content-between align-items-center mb-1">
    <label class="form-label small mb-0">Personas activas de la empresa seleccionada</label>
    <div id="am-todas" style="display:none">
      <button type="button" id="am-sel-todas" class="btn btn-link btn-sm p-0 me-2">Seleccionar todas</button>
      <button type="button" id="am-sel-ninguna" class="btn btn-link btn-sm p-0 text-muted">Ninguna</button>
    </div>
  </div>
  <div id="am-personas" class="border rounded p-2 mb-3" style="max-height:320px;overflow:auto">
    {% for e in emps_obra %}
    <div class="am-grp" data-emp="{{ e.id_empresa }}" style="display:none">
      {% for p in pers_x_emp[e.id_empresa] %}
      <div class="form-check">
        <input class="form-check-input" type="checkbox" name="personas" value="{{ p.id_persona }}"
               id="am-p{{ p.id_persona }}" disabled>
        <label class="form-check-label small" for="am-p{{ p.id_persona }}">
          {{ p.apellido1 }} {{ p.apellido2 }}, {{ p.nombre }} <span class="text-muted">({{ p.oficio }})</span>
        </label>
      </div>
      {% else %}
      <p class="text-muted small mb-0">Sin personas activas en esta empresa.</p>
      {% endfor %}
    </div>
    {% endfor %}
    <p class="text-muted small mb-0" id="am-hint">Selecciona una empresa para ver su personal.</p>
  </div>
  <button type="submit" class="btn btn-opl btn-sm" {{ 'disabled' if not emps_obra }}><i class="bi bi-check2-all"></i> Asignar a los seleccionados</button>
</form>
</div></div>
{% endblock %}
{% block scripts %}
<script>
(function(){
  var sel = document.getElementById('am-emp');
  if (!sel) return;   // obra sin empresas: no hay nada que sincronizar

  function sync(){
    var v = sel.value;
    document.querySelectorAll('.am-grp').forEach(function(g){
      var on = g.dataset.emp === v;
      g.style.display = on ? 'block' : 'none';
      g.querySelectorAll('input[type=checkbox]').forEach(function(cb){
        cb.disabled = !on;
        if (!on) cb.checked = false;
      });
    });
    document.getElementById('am-hint').style.display = v ? 'none' : 'block';
    document.getElementById('am-todas').style.display = v ? 'block' : 'none';
  }

  document.getElementById('am-sel-todas').addEventListener('click', function(){
    document.querySelectorAll('.am-grp[data-emp="' + sel.value + '"] input[type=checkbox]:not(:disabled)')
      .forEach(function(cb){ cb.checked = true; });
  });
  document.getElementById('am-sel-ninguna').addEventListener('click', function(){
    document.querySelectorAll('.am-grp[data-emp="' + sel.value + '"] input[type=checkbox]')
      .forEach(function(cb){ cb.checked = false; });
  });

  sel.addEventListener('change', sync);
  // Si solo hay una empresa vinculada a la obra, la seleccionamos directamente
  // para no obligar a un clic extra. También cubre el caso de que el
  // navegador restaure un valor previo (al volver atrás) sin disparar 'change'.
  {% if emps_obra|length == 1 %}
  sel.value = '{{ emps_obra[0].id_empresa }}';
  {% endif %}
  sync();
})();
</script>
{% endblock %}
""", obra=obra, d=d, emps_obra=emps_obra, partidas=partidas, pers_x_emp=pers_x_emp)

# -- MENSUAL --
@app.route('/mensual/')
def mensual_sel():
    db = get_db()
    mens = db.execute("""SELECT m.*, o.nombre nom_o, o.codigo cod_o, e.nombre nom_e
        FROM mensual m JOIN obra o ON m.id_obra=o.id_obra JOIN empresa e ON m.id_empresa=e.id_empresa
        ORDER BY m.mes DESC, o.nombre, e.nombre""").fetchall()
    obras = db.execute("SELECT * FROM obra WHERE estado='activa' ORDER BY nombre").fetchall()
    emps  = db.execute("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").fetchall()
    hoy_mes = fs(date_type.today())[:7]
    return render_template_string(BASE + r"""
{% block am %}hi{% endblock %}{% block title %}Mensuales{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h2 class="h4 mb-0"><i class="bi bi-calendar-month"></i> Mensuales</h2>
</div>
<div class="row g-3">
<div class="col-md-4">
  <div class="card"><div class="card-header">Nuevo / abrir mensual</div><div class="card-body">
  <form method="post" action="/mensual/nuevo">
    <div class="mb-2"><label class="form-label small">Obra *</label>
      <select name="id_obra" class="form-select form-select-sm" required>
        <option value="">— Selecciona —</option>
        {% for o in obras %}<option value="{{ o.id_obra }}">{{ o.codigo }} — {{ o.nombre }}</option>{% endfor %}
      </select></div>
    <div class="mb-2"><label class="form-label small">Empresa principal *</label>
      <select name="id_empresa" class="form-select form-select-sm" required>
        <option value="">— Selecciona —</option>
        {% for e in emps %}<option value="{{ e.id_empresa }}">{{ e.nombre }}</option>{% endfor %}
      </select></div>
    <div class="mb-3"><label class="form-label small">Mes *</label>
      <input type="month" name="mes" class="form-control form-control-sm" value="{{ hoy_mes }}" required></div>
    <button type="submit" class="btn btn-opl btn-sm w-100">Crear / Abrir</button>
  </form></div></div>
</div>
<div class="col-md-8">
  <div class="card"><div class="card-body p-0">
  <table class="table table-hover mb-0 table-sm">
    <thead><tr><th>Mes</th><th>Obra</th><th>Empresa</th><th>Estado</th><th class="text-end">Acciones</th></tr></thead>
    <tbody>
    {% for m in mens %}
    <tr>
      <td class="font-monospace fw-bold">{{ m.mes }}</td>
      <td>{{ m.nom_o }}<br><small class="text-muted">{{ m.cod_o }}</small></td>
      <td>{{ m.nom_e }}</td>
      <td><span class="badge badge-{{ m.estado }}">{{ m.estado }}</span></td>
      <td class="text-end">
        <a href="/mensual/{{ m.id_mensual }}" class="btn btn-sm btn-outline-secondary py-0"><i class="bi bi-eye"></i></a>
        {% if m.estado=='cerrado' %}
        <a href="/mensual/{{ m.id_mensual }}/csv" class="btn btn-sm btn-outline-success py-0"><i class="bi bi-download"></i></a>
        {% endif %}
      </td>
    </tr>
    {% else %}
    <tr><td colspan="5" class="text-center py-4 text-muted">Sin mensuales.</td></tr>
    {% endfor %}
    </tbody>
  </table></div></div>
</div></div>
{% endblock %}
""", mens=mens, obras=obras, emps=emps, hoy_mes=hoy_mes)

@app.route('/mensual/nuevo', methods=['POST'])
def mensual_nuevo():
    db = get_db()
    io = request.form.get('id_obra', type=int)
    ie = request.form.get('id_empresa', type=int)
    m  = request.form.get('mes','').strip()
    if not io or not ie or not m:
        flash('Todos los campos son obligatorios.', 'error'); return redirect(url_for('mensual_sel'))
    try:
        _chk_obra_activa(io)
        db.execute('INSERT OR IGNORE INTO mensual(id_obra,id_empresa,mes) VALUES(?,?,?)', [io,ie,m]); db.commit()
        mid = db.execute('SELECT id_mensual FROM mensual WHERE id_obra=? AND id_empresa=? AND mes=?', [io,ie,m]).fetchone()['id_mensual']
        return redirect(url_for('mensual_ver', id_m=mid))
    except ValueError as e:
        flash(str(e), 'error'); return redirect(url_for('mensual_sel'))
    except Exception as e:
        flash(f'Error: {e}', 'error'); return redirect(url_for('mensual_sel'))

@app.route('/mensual/<int:id_m>')
def mensual_ver(id_m):
    db = get_db()
    m = db.execute("""SELECT m.*, o.nombre nom_o, o.codigo cod_o, o.estado estado_obra, e.nombre nom_e
        FROM mensual m JOIN obra o ON m.id_obra=o.id_obra JOIN empresa e ON m.id_empresa=e.id_empresa
        WHERE m.id_mensual=?""", [id_m]).fetchone()
    if not m: flash('No encontrado.', 'error'); return redirect(url_for('mensual_sel'))

    year, month = int(m['mes'][:4]), int(m['mes'][5:])
    days = calendar.monthrange(year, month)[1]

    if m['estado'] == 'cerrado':
        filas = []
        for f in db.execute("SELECT mp.* FROM mensual_persona mp WHERE mp.id_mensual=? ORDER BY mp.es_subcontrata,mp.empresa_cache,mp.ap1_c,mp.nom_c", [id_m]).fetchall():
            dias_arr = [f[f'd{i}'] for i in range(1, days+1)]
            filas.append({**dict(f), 'dias_arr': dias_arr})
    else:
        filas, _ = _calcular_filas_mensual(m['id_obra'], m['id_empresa'], m['mes'])

    return render_template_string(BASE + _MENSUAL_TPL,
                                  m=m, filas=filas, days=days, hhmm=hhmm,
                                  dias_num=list(range(1, days+1)))

@app.route('/mensual/<int:id_m>/cerrar', methods=['POST'])
def mensual_cerrar(id_m):
    db = get_db()
    m = db.execute("""SELECT mn.*, o.nombre nom_o, e.nombre nom_e FROM mensual mn
        JOIN obra o ON mn.id_obra=o.id_obra JOIN empresa e ON mn.id_empresa=e.id_empresa
        WHERE mn.id_mensual=?""", [id_m]).fetchone()
    if not m: flash('No encontrado.', 'error'); return redirect(url_for('mensual_sel'))
    filas, days = _calcular_filas_mensual(m['id_obra'], m['id_empresa'], m['mes'])
    db.execute('DELETE FROM mensual_persona WHERE id_mensual=?', [id_m])
    for g in filas:
        dias_vals = [g['dias_arr'][i] if i < len(g['dias_arr']) else None for i in range(31)]
        dcols = ','.join(f'd{i+1}' for i in range(31))
        dmarks= ','.join(['?']*31)
        db.execute(f"""INSERT INTO mensual_persona
            (id_mensual,id_persona,id_rango,id_empresa,nom_c,ap1_c,ap2_c,dni_c,
             rango_cache,empresa_cache,es_subcontrata,{dcols},total_mes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,{dmarks},?)""",
                   [id_m, g['id_persona'], g['id_rango'], g['id_empresa'],
                    g['nom_c'], g['ap1_c'], g['ap2_c'], g['dni_c'],
                    g['rango_cache'], g['empresa_cache'], g['es_subcontrata']]
                   + dias_vals + [g['total_mes']])
    db.execute("UPDATE mensual SET estado='cerrado' WHERE id_mensual=?", [id_m])
    log_event('CIERRE_MENSUAL', 'mensual', id_m, m['id_obra'],
             {'obra_nombre': m['nom_o'], 'empresa_id': m['id_empresa'], 'empresa_nombre': m['nom_e'], 'mes': m['mes']})
    db.commit()
    flash('Mes cerrado. Snapshot generado.', 'success')
    return redirect(url_for('mensual_ver', id_m=id_m))

@app.route('/mensual/<int:id_m>/reabrir', methods=['POST'])
def mensual_reabrir(id_m):
    db = get_db()
    m = db.execute("""SELECT mn.*, o.nombre nom_o, e.nombre nom_e FROM mensual mn
        JOIN obra o ON mn.id_obra=o.id_obra JOIN empresa e ON mn.id_empresa=e.id_empresa
        WHERE mn.id_mensual=?""", [id_m]).fetchone()
    if not m: flash('No encontrado.', 'error'); return redirect(url_for('mensual_sel'))
    try:
        _chk_obra_activa(m['id_obra'])
    except ValueError as e:
        flash(str(e), 'error'); return redirect(url_for('mensual_ver', id_m=id_m))
    motivo = request.form.get('motivo','').strip()
    db.execute("UPDATE mensual SET estado='abierto' WHERE id_mensual=?", [id_m])
    db.execute("DELETE FROM mensual_persona WHERE id_mensual=?", [id_m])
    detalle = {'obra_nombre': m['nom_o'], 'empresa_id': m['id_empresa'], 'empresa_nombre': m['nom_e'], 'mes': m['mes']}
    if motivo: detalle['motivo'] = motivo
    log_event('REABRIR_MENSUAL', 'mensual', id_m, m['id_obra'], detalle)
    db.commit(); flash('Mes reabierto. El snapshot anterior fue eliminado.', 'warning')
    return redirect(url_for('mensual_ver', id_m=id_m))

@app.route('/mensual/<int:id_m>/csv')
def mensual_csv(id_m):
    db = get_db()
    m = db.execute("""SELECT m.*, o.nombre nom_o, o.codigo cod_o, e.nombre nom_e
        FROM mensual m JOIN obra o ON m.id_obra=o.id_obra JOIN empresa e ON m.id_empresa=e.id_empresa
        WHERE m.id_mensual=?""", [id_m]).fetchone()
    if not m: flash('No encontrado.', 'error'); return redirect(url_for('mensual_sel'))
    if m['estado'] != 'cerrado':
        flash('Cierra el mes antes de exportar.', 'warning'); return redirect(url_for('mensual_ver', id_m=id_m))

    year, month = int(m['mes'][:4]), int(m['mes'][5:])
    days = calendar.monthrange(year, month)[1]

    out = io.StringIO()
    w   = csv.writer(out, delimiter=';')
    w.writerow(['Empresa','Subcontrata','Rango','Apellidos','Nombre','DNI'] +
               [f'Dia_{i}' for i in range(1, days+1)] + ['Total_mes'])

    for f in db.execute("SELECT mp.* FROM mensual_persona mp WHERE mp.id_mensual=? ORDER BY mp.es_subcontrata,mp.empresa_cache,mp.ap1_c,mp.nom_c", [id_m]).fetchall():
        fila = [f['empresa_cache'], 'Sí' if f['es_subcontrata'] else 'No',
                f['rango_cache'], f['ap1_c']+' '+f['ap2_c'], f['nom_c'], f['dni_c']]
        fila += [hhmm(f[f'd{i}']) for i in range(1, days+1)]
        fila += [hhmm(f['total_mes'])]
        w.writerow(fila)

    nombre = f"mensual_{m['mes']}_{norm(m['nom_o'])}_{norm(m['nom_e'])}.csv"
    return Response(out.getvalue(), mimetype='text/csv; charset=utf-8-sig',
                    headers={'Content-Disposition': f'attachment; filename="{nombre}"'})

_MENSUAL_TPL = r"""
{% block am %}hi{% endblock %}
{% block title %}Mensual {{ m.mes }}{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
  <div>
    <h2 class="h4 mb-0"><i class="bi bi-calendar-month"></i> {{ m.nom_o }} / {{ m.nom_e }}
      <span class="badge badge-{{ m.estado }} ms-1">{{ m.estado }}</span>
    </h2>
    <small class="text-muted">{{ m.mes }} — {{ m.cod_o }}</small>
  </div>
  <div class="d-flex gap-2 flex-wrap align-items-start">
    {% if m.estado=='abierto' %}
    <form method="post" action="/mensual/{{ m.id_mensual }}/cerrar"
          onsubmit="return confirm('¿Cerrar el mes y generar snapshot? El cierre es definitivo (excepto si lo reabriste)')">
      <button class="btn btn-warning btn-sm"><i class="bi bi-lock"></i> Cerrar mes</button>
    </form>
    {% else %}
    <a href="/mensual/{{ m.id_mensual }}/csv" class="btn btn-success btn-sm">
      <i class="bi bi-download"></i> Exportar CSV</a>
    {% if m.estado_obra == 'finalizada' %}
    <span class="btn btn-outline-secondary btn-sm disabled"><i class="bi bi-unlock"></i> Reabrir (obra finalizada)</span>
    {% else %}
    <form method="post" action="/mensual/{{ m.id_mensual }}/reabrir" class="d-flex gap-1"
          onsubmit="return confirm('¿Reabrir? El snapshot actual se eliminará.')">
      <input type="text" name="motivo" class="form-control form-control-sm" placeholder="Motivo (opcional)" style="width:180px">
      <button class="btn btn-outline-warning btn-sm text-nowrap"><i class="bi bi-unlock"></i> Reabrir</button>
    </form>
    {% endif %}
    {% endif %}
    <a href="/obras/{{ m.id_obra }}/estado" class="btn btn-outline-warning btn-sm" title="Estado de obra"><i class="bi bi-clipboard-data"></i></a>
    <a href="/mensual/" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left"></i></a>
  </div>
</div>

{% if filas %}
<div class="table-responsive">
<table class="table table-sm table-bordered mb-0" style="font-size:.74rem">
  <thead>
    <tr class="table-dark">
      <th>Empresa</th><th>Sub</th><th>Rango</th><th>Apellidos, Nombre</th><th>DNI</th>
      {% for i in dias_num %}<th class="hth">{{ i }}</th>{% endfor %}
      <th class="hth text-warning">Total</th>
    </tr>
  </thead>
  <tbody>
  {% set ns = namespace(last_sub=-1) %}
  {% for f in filas %}
  {% if ns.last_sub != f.es_subcontrata and f.es_subcontrata == 1 %}
  <tr><td colspan="{{ 5 + days + 1 }}" class="text-center text-muted py-1 small">
    <i class="bi bi-diagram-3"></i> Subcontratas
  </td></tr>
  {% set ns.last_sub = 1 %}
  {% endif %}
  <tr class="{{ 'table-secondary' if f.es_subcontrata else '' }}">
    <td class="small">{{ f.empresa_cache }}</td>
    <td class="text-center">{{ '✓' if f.es_subcontrata else '' }}</td>
    <td><span class="badge bg-secondary" style="font-size:.62rem">{{ f.rango_cache or '—' }}</span></td>
    <td>{{ f.ap1_c }} {{ f.ap2_c }}, {{ f.nom_c }}</td>
    <td class="font-monospace" style="font-size:.68rem">{{ f.dni_c }}</td>
    {% for h in f.dias_arr %}<td class="htd">{{ hhmm(h) }}</td>{% endfor %}
    <td class="htd fw-bold text-warning">{{ hhmm(f.total_mes) }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table></div>
{% else %}
<div class="alert alert-info">Sin datos. Añade partes diarios primero.</div>
{% endif %}
{% endblock %}"""

# -- BACKUP --
@app.route('/backup/')
def backup_page():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bks   = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')], reverse=True)
    obras = get_db().execute("SELECT * FROM obra ORDER BY nombre").fetchall()
    return render_template_string(BASE + r"""
{% block title %}Backup{% endblock %}
{% block content %}
<h2 class="h4 mb-3"><i class="bi bi-hdd"></i> Copias de seguridad</h2>
<div class="row g-3">
<div class="col-md-4">
  <div class="card"><div class="card-header">Crear backup</div><div class="card-body">
  <form method="post" action="/backup/crear">
    <div class="mb-2"><label class="form-label small">Contexto (obra)</label>
      <select name="id_obra" class="form-select form-select-sm">
        <option value="">Sin contexto (General)</option>
        {% for o in obras %}<option value="{{ o.id_obra }}">{{ o.codigo }} — {{ o.nombre }}</option>{% endfor %}
      </select></div>
    <div class="alert alert-secondary small py-2 mb-3">
      <i class="bi bi-info-circle"></i> Siempre se copia <strong>toda</strong> la BD,
      independientemente del contexto.
    </div>
    <button type="submit" class="btn btn-opl btn-sm w-100">
      <i class="bi bi-cloud-download"></i> Crear backup ahora
    </button>
  </form></div></div>
</div>
<div class="col-md-8">
  <div class="card"><div class="card-body p-0">
  <table class="table table-hover mb-0 table-sm">
    <thead><tr><th>Fichero de backup</th><th class="text-end">Acción</th></tr></thead>
    <tbody>
    {% for b in bks %}
    <tr>
      <td class="font-monospace small">{{ b }}</td>
      <td class="text-end">
        <form method="post" action="/backup/restaurar" class="d-inline"
              onsubmit="return confirm('ATENCIÓN\n\nRestaurar este backup reemplazará TODOS los datos actuales.\nEs un borrón y cuenta nueva. Los cambios posteriores al backup se perderán.\n\n¿Continuar?')">
          <input type="hidden" name="nombre" value="{{ b }}">
          <button class="btn btn-sm btn-outline-warning">
            <i class="bi bi-arrow-counterclockwise"></i> Restaurar
          </button>
        </form>
      </td>
    </tr>
    {% else %}
    <tr><td colspan="2" class="text-center py-4 text-muted">Sin backups.</td></tr>
    {% endfor %}
    </tbody>
  </table></div></div>
</div></div>
{% endblock %}
""", bks=bks, obras=obras)

@app.route('/backup/crear', methods=['POST'])
def backup_crear():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    id_obra = request.form.get('id_obra', type=int)
    ctx = 'GENERAL'
    if id_obra:
        ob = get_db().execute('SELECT codigo,nombre FROM obra WHERE id_obra=?', [id_obra]).fetchone()
        if ob: ctx = f"{ob['codigo']}_{norm(ob['nombre'])}"
    nombre = f"backup_{datetime.now().strftime('%Y%m%d_%H%M')}_{ctx}.db"
    ruta   = os.path.join(BACKUP_DIR, nombre)
    try:
        src = sqlite3.connect(DB_PATH); dst = sqlite3.connect(ruta)
        with dst: src.backup(dst)
        src.close(); dst.close()
        flash(f'Backup creado: {nombre}', 'success')
    except Exception as e: flash(f'Error: {e}', 'error')
    return redirect(url_for('backup_page'))

@app.route('/backup/restaurar', methods=['POST'])
def backup_restaurar():
    nombre = request.form.get('nombre','').strip()
    ruta   = os.path.join(BACKUP_DIR, nombre)
    if not os.path.exists(ruta):
        flash('Backup no encontrado.', 'error'); return redirect(url_for('backup_page'))
    try:
        close_db(); shutil.copy2(ruta, DB_PATH)
        flash(f'BD restaurada desde: {nombre}. Recarga la aplicación.', 'success')
    except Exception as e: flash(f'Error: {e}', 'error')
    return redirect(url_for('backup_page'))

# -- CONFIG --
@app.route('/config/', methods=['GET','POST'])
def configuracion():
    db = get_db()
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'reset':
            db.execute('UPDATE config SET limite_horas_dia=24.0 WHERE id_config=1')
            db.commit(); flash('Límite restablecido a 24 h/día.', 'success')
        elif accion == 'guardar':
            try:
                lim = float(request.form['limite'])
                if lim <= 0: raise ValueError
                db.execute('UPDATE config SET limite_horas_dia=? WHERE id_config=1', [lim])
                db.commit(); flash(f'Límite actualizado a {hhmm(lim)}.', 'success')
            except: flash('Valor inválido.', 'error')
        return redirect(url_for('configuracion'))
    lim = get_lim()
    return render_template_string(BASE + r"""
{% block ac %}hi{% endblock %}{% block title %}Config{% endblock %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-5">
<div class="card"><div class="card-header"><h5 class="mb-0"><i class="bi bi-gear"></i> Configuración</h5></div>
<div class="card-body">
  <div class="sec">Límite de horas por persona y día</div>
  <p class="text-muted small">Si una persona supera este total en un día (sumando todas las obras y empresas), la línea no se guarda.</p>
  <form method="post" class="mb-3">
    <div class="input-group input-group-sm">
      <input type="number" name="limite" class="form-control" value="{{ lim }}" step="0.5" min="0.5">
      <span class="input-group-text">h/día &nbsp;(ahora: <strong>{{ hhmm(lim) }}</strong>)</span>
      <button name="accion" value="guardar" class="btn btn-opl">Guardar</button>
    </div>
  </form>
  <form method="post">
    <button name="accion" value="reset" class="btn btn-outline-secondary btn-sm"
            onclick="return confirm('¿Restablecer a 24 h/día?')">
      <i class="bi bi-arrow-counterclockwise"></i> Restablecer a 24 h/día
    </button>
  </form>
  <hr>
  <a href="/config/metas" class="btn btn-outline-secondary btn-sm w-100"><i class="bi bi-bullseye"></i> Metas de horas →</a>
</div></div></div></div>
{% endblock %}
""", lim=lim, hhmm=hhmm)

# -- CONFIG: METAS DE HORAS (4.4) --
@app.route('/config/metas', methods=['GET','POST'])
def config_metas():
    db = get_db()
    if request.method == 'POST':
        try:
            umbral = float(request.form['umbral_desajuste_meta'])
            if umbral < 0: raise ValueError
            db.execute('UPDATE config SET umbral_desajuste_meta=? WHERE id_config=1', [umbral])
            db.commit(); flash(f'Umbral de desajuste actualizado a {hhmm(umbral)}.', 'success')
        except ValueError:
            flash('Umbral inválido.', 'error')
        return redirect(url_for('config_metas'))
    empresas = db.execute("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").fetchall()
    obras    = db.execute("SELECT * FROM obra ORDER BY (estado='finalizada'), nombre").fetchall()
    personas = db.execute("""SELECT p.*, e.nombre nom_e FROM persona p LEFT JOIN empresa e ON p.id_empresa=e.id_empresa
                             WHERE p.estado='activa' ORDER BY p.apellido1, p.nombre""").fetchall()
    umbral = get_umbral_desajuste()
    avisos = _listar_desajustes_meta()
    return render_template_string(BASE + r"""
{% block ac %}hi{% endblock %}{% block title %}Metas de horas{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h2 class="h4 mb-0"><i class="bi bi-bullseye"></i> Metas de horas</h2>
  <a href="/config/" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left"></i> Config general</a>
</div>
<p class="text-muted small">Meta efectiva por jornada: <strong>persona</strong> &gt; <strong>empresa</strong> &gt; <strong>obra</strong> &gt; 8h por defecto.
La meta de una persona siempre prevalece sobre la de su empresa y obra.</p>

<div class="card mb-3"><div class="card-body">
  <div class="sec mb-2">Umbral de desajuste persona/empresa</div>
  <form method="post" class="row g-2 align-items-center">
    <div class="col-auto">
      <div class="input-group input-group-sm">
        <input type="number" name="umbral_desajuste_meta" class="form-control" value="{{ umbral }}" step="0.25" min="0">
        <span class="input-group-text">h (ahora: {{ hhmm(umbral) }})</span>
        <button class="btn btn-opl">Guardar</button>
      </div>
    </div>
  </form>
  <div class="form-text">Si la meta de una persona difiere de la de su empresa en al menos este umbral, se avisa
    aquí y al vincular la persona a la empresa (no en cada fichaje diario).</div>
</div></div>

{% if avisos %}
<div class="alert alert-warning">
  <strong><i class="bi bi-exclamation-triangle"></i> Desajustes detectados:</strong>
  <ul class="mb-0 small">{% for a in avisos %}<li>{{ a }}</li>{% endfor %}</ul>
</div>
{% endif %}

<div class="row g-3">
<div class="col-md-4">
  <div class="card"><div class="card-header">Empresas</div><div class="card-body p-0">
  <table class="table table-sm mb-0">
  {% for e in empresas %}
  <tr><td class="small">{{ e.nombre }}</td>
    <td style="width:110px">
      <form method="post" action="/config/metas/empresa/{{ e.id_empresa }}" class="d-flex gap-1">
        <input type="number" name="meta_horas_dia" class="form-control form-control-sm" step="0.25" min="0.25"
               value="{{ e.meta_horas_dia if e.meta_horas_dia is not none else '' }}" placeholder="8h">
        <button class="btn btn-sm btn-outline-secondary py-0"><i class="bi bi-check"></i></button>
      </form>
    </td>
  </tr>
  {% endfor %}
  </table></div></div>
</div>
<div class="col-md-4">
  <div class="card"><div class="card-header">Obras</div><div class="card-body p-0">
  <table class="table table-sm mb-0">
  {% for o in obras %}
  <tr><td class="small">{{ o.nombre }} {% if o.estado=='finalizada' %}<span class="badge badge-finalizada">fin.</span>{% endif %}</td>
    <td style="width:110px">
      {% if o.estado == 'finalizada' %}
      <span class="small text-muted">{{ hhmm(o.meta_horas_dia) if o.meta_horas_dia is not none else '—' }} (solo lectura)</span>
      {% else %}
      <form method="post" action="/config/metas/obra/{{ o.id_obra }}" class="d-flex gap-1">
        <input type="number" name="meta_horas_dia" class="form-control form-control-sm" step="0.25" min="0.25"
               value="{{ o.meta_horas_dia if o.meta_horas_dia is not none else '' }}" placeholder="8h">
        <button class="btn btn-sm btn-outline-secondary py-0"><i class="bi bi-check"></i></button>
      </form>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
  </table></div></div>
</div>
<div class="col-md-4">
  <div class="card"><div class="card-header">Personas</div><div class="card-body p-0" style="max-height:420px;overflow:auto">
  <table class="table table-sm mb-0">
  {% for p in personas %}
  <tr><td class="small">{{ p.apellido1 }}, {{ p.nombre }}<br><span class="text-muted" style="font-size:.68rem">{{ p.nom_e or '—' }}</span></td>
    <td style="width:110px">
      <form method="post" action="/config/metas/persona/{{ p.id_persona }}" class="d-flex gap-1">
        <input type="number" name="meta_horas_dia" class="form-control form-control-sm" step="0.25" min="0.25"
               value="{{ p.meta_horas_dia if p.meta_horas_dia is not none else '' }}" placeholder="—">
        <button class="btn btn-sm btn-outline-secondary py-0"><i class="bi bi-check"></i></button>
      </form>
    </td>
  </tr>
  {% endfor %}
  </table></div></div>
</div>
</div>
{% endblock %}
""", empresas=empresas, obras=obras, personas=personas, umbral=umbral, avisos=avisos, hhmm=hhmm)

def _guardar_meta(tabla, pk, id_):
    raw = request.form.get('meta_horas_dia','').strip()
    db = get_db()
    try:
        meta = float(raw) if raw else None
        if meta is not None and meta <= 0: raise ValueError
        db.execute(f'UPDATE {tabla} SET meta_horas_dia=? WHERE {pk}=?', [meta, id_])
        db.commit(); flash('Meta actualizada.', 'success')
    except ValueError:
        flash('Meta de horas inválida.', 'error')

@app.route('/config/metas/persona/<int:id_>', methods=['POST'])
def config_meta_persona(id_):
    _guardar_meta('persona', 'id_persona', id_)
    return redirect(url_for('config_metas'))

@app.route('/config/metas/empresa/<int:id_>', methods=['POST'])
def config_meta_empresa(id_):
    _guardar_meta('empresa', 'id_empresa', id_)
    return redirect(url_for('config_metas'))

@app.route('/config/metas/obra/<int:id_>', methods=['POST'])
def config_meta_obra(id_):
    ob = get_db().execute('SELECT estado FROM obra WHERE id_obra=?', [id_]).fetchone()
    if ob and ob['estado'] == 'finalizada':
        flash('La obra está finalizada: la meta de horas no es editable.', 'error')
        return redirect(url_for('config_metas'))
    _guardar_meta('obra', 'id_obra', id_)
    return redirect(url_for('config_metas'))

# -- INFORMES: COSTES (4.5) --
@app.route('/informes/costes')
def informes_costes():
    db = get_db()
    obras = db.execute('SELECT * FROM obra ORDER BY nombre').fetchall()
    id_obra = request.args.get('id_obra', type=int)
    mes_str = request.args.get('mes', '').strip() or fs(date_type.today())[:7]
    filas = dias_tabla = None
    total_horas = total_coste = 0
    obra_sel = None
    if id_obra:
        obra_sel = db.execute('SELECT * FROM obra WHERE id_obra=?', [id_obra]).fetchone()
        if obra_sel:
            filas, dias_tabla, total_horas, total_coste, _ = _informe_costes(id_obra, mes_str)
    return render_template_string(BASE + r"""
{% block ain %}hi{% endblock %}{% block title %}Informe de costes{% endblock %}
{% block content %}
<h2 class="h4 mb-3"><i class="bi bi-cash-coin"></i> Informe de costes</h2>
<p class="text-muted small"><i class="bi bi-info-circle"></i> Los costes se calculan al vuelo con las tarifas y precios
  vigentes en este momento; no se almacenan. Vista solo administrativa: no se muestran precios en el diario ni en el mensual operativo.</p>
<div class="card mb-3"><div class="card-body">
<form method="get" class="row g-2 align-items-end">
  <div class="col-md-4"><label class="form-label small mb-1">Obra</label>
    <select name="id_obra" class="form-select form-select-sm" required>
      <option value="">— Selecciona —</option>
      {% for o in obras %}<option value="{{ o.id_obra }}" {{ 'selected' if obra_sel and o.id_obra==obra_sel.id_obra }}>{{ o.nombre }}</option>{% endfor %}
    </select></div>
  <div class="col-md-3"><label class="form-label small mb-1">Mes</label>
    <input type="month" name="mes" class="form-control form-control-sm" value="{{ mes_str }}"></div>
  <div class="col-auto"><button class="btn btn-opl btn-sm">Ver informe</button></div>
</form>
</div></div>

{% if obra_sel %}
<h5 class="mb-2">{{ obra_sel.nombre }} — {{ mes_str }}</h5>
<div class="row g-3 mb-3">
  <div class="col-md-6">
    <div class="card"><div class="card-header">Coste total por persona y mes</div><div class="card-body p-0">
    <table class="table table-sm mb-0" style="font-size:.78rem">
      <thead><tr><th>Empresa</th><th>Persona</th><th class="text-end">Horas</th><th class="text-end">€/h</th><th class="text-end">Coste</th></tr></thead>
      <tbody>
      {% for f in filas %}
      <tr><td class="small">{{ f.empresa }}</td><td class="small">{{ f.nombre }}</td>
        <td class="text-end">{{ hhmm(f.horas) }}</td>
        <td class="text-end">{{ '%.2f'|format(f.precio_hora) if f.precio_hora else '—' }}</td>
        <td class="text-end fw-bold">{{ '%.2f €'|format(f.coste) }}</td></tr>
      {% else %}
      <tr><td colspan="5" class="text-center text-muted py-3">Sin actividad este mes.</td></tr>
      {% endfor %}
      </tbody>
      <tfoot><tr class="table-dark"><th colspan="2">Total</th><th class="text-end">{{ hhmm(total_horas) }}</th><th></th>
        <th class="text-end">{{ '%.2f €'|format(total_coste) }}</th></tr></tfoot>
    </table></div></div>
  </div>
  <div class="col-md-6">
    <div class="card"><div class="card-header">Coste total por obra/día</div><div class="card-body p-0" style="max-height:420px;overflow:auto">
    <table class="table table-sm mb-0" style="font-size:.78rem">
      <thead><tr><th>Día</th><th class="text-end">Horas</th><th class="text-end">Coste</th></tr></thead>
      <tbody>
      {% for dd in dias_tabla %}
      <tr><td>{{ dd.dia }}</td><td class="text-end">{{ hhmm(dd.horas) }}</td>
        <td class="text-end">{{ '%.2f €'|format(dd.coste) }}</td></tr>
      {% endfor %}
      </tbody>
    </table></div></div>
  </div>
</div>
{% endif %}
{% endblock %}
""", obras=obras, obra_sel=obra_sel, mes_str=mes_str, filas=filas, dias_tabla=dias_tabla,
     total_horas=total_horas, total_coste=total_coste, hhmm=hhmm)

# -- FAQ --
@app.route('/faq/')
def faq():
    preguntas = [
        ('¿Qué es el límite de horas por día?',
         'El máximo de horas que puede acumular una persona en un día, sumando todas las obras y empresas. '
         'Por defecto 24 h. Se configura en <strong>Config</strong>. Si se supera, la línea no se guarda y se muestra un error.'),
        ('¿Qué pasa al cerrar un mes?',
         'Se genera un <strong>snapshot</strong> que congela: nombres, DNIs, rangos y horas de cada persona. '
         'No se puede modificar desde la app. Si necesitas corregir algo, haz backup primero y luego reabre el mes.'),
        ('¿Puedo reabrir un mes cerrado?',
         'Sí, con el botón <em>Reabrir</em>. El snapshot anterior <strong>se borra</strong>. '
         'Al recalcular puede haber diferencias si se modificaron diarios o maestros. '
         'Los CSVs ya exportados <strong>no se actualizan</strong>.'),
        ('¿Qué hace el backup y cuándo hacerlo?',
         'Copia <em>toda</em> la base de datos en la carpeta <code>backups/</code>. '
         '<strong>Hazlo antes de cerrar un mes, borrar obras/empresas o restaurar otro backup.</strong>'),
        ('¿Qué implica restaurar un backup?',
         'Es un <strong>borrón y cuenta nueva</strong>: todos los datos actuales se reemplazan. '
         'Los cambios posteriores al backup se pierden. Úsalo solo en caso de error grave.'),
        ('¿Por qué las horas se muestran en HH:MM?',
         'Internamente se guardan como decimales (7.5 h) para sumar correctamente. '
         'Se muestran como <code>07:30</code> para facilitar la lectura en pantalla y en Excel.'),
        ('¿Qué es el arrastre de parte?',
         'El botón <em>Arrastrar de [fecha]</em> copia las personas y asuntos del último diario disponible '
         'de esa obra. Las horas se ponen a <strong>0</strong> para que las revises. '
         'Si una persona ya está en el parte actual, no se duplica.'),
        ('¿Qué son las subcontratas?',
         'En <em>Maestros → Subcontratas</em> defines que la empresa A subcontrata a B. '
         'Al generar o cerrar el mensual de A, se incluyen también las horas de trabajadores de B, '
         'marcados con ✓ en la columna Sub.'),
        ('¿Qué es el rango profesional?',
         'Cada persona tiene un rango (Peón, Oficial 1ª, Capataz…). '
         'Al añadir una línea en el diario se usa el rango activo en esa fecha. '
         'El historial de rangos se conserva aunque cambie. En el mensual aparece el rango del momento.'),
        ('¿Qué son las partidas de obra?',
         'Cada obra puede tener fases (ej. <code>1.1 Movimiento de tierras</code>). '
         'Se asignan en las líneas del diario para clasificar el trabajo por fase.'),
        ('¿Cómo abrir el CSV en Excel?',
         'Excel → Datos → Obtener datos → Desde texto/CSV → selecciona el fichero. '
         'Usa punto y coma (;) como separador. Las columnas de horas son texto <code>HH:MM</code>.'),
        ('¿Qué es la meta de horas/día? <span class="badge bg-warning text-dark">v1.2</span>',
         'Es la jornada esperada de una persona. Se calcula así: <strong>meta de la persona</strong> '
         '(si tiene una propia) &gt; <strong>meta de su empresa</strong> &gt; <strong>meta de la obra</strong> '
         '&gt; 8 h por defecto. Se edita en <em>Config → Metas de horas</em>. No bloquea nada: solo avisa '
         '(por ejemplo, en la asignación masiva si asignas menos horas de la meta).'),
        ('¿Qué es el desajuste de meta persona/empresa? <span class="badge bg-warning text-dark">v1.2</span>',
         'Si la meta de una persona y la de su empresa difieren más del "umbral de desajuste" configurado, '
         'se muestra un aviso al vincular la persona a la empresa y en <em>Config → Metas de horas</em>. '
         'Es solo informativo, no bloquea el fichaje diario.'),
        ('¿Cómo funcionan los costes por hora? <span class="badge bg-warning text-dark">v1.2</span>',
         'Cada rango puede tener un precio/hora en <em>Maestros → Rangos</em>. Una persona puede tener un '
         'precio propio (override) que prevalece sobre el de su rango. Los costes solo se ven en '
         '<em>Informes → Costes</em>; nunca se muestran en el diario ni en el mensual operativo, y no se '
         'guardan: se recalculan cada vez con los precios vigentes.'),
        ('¿Qué es la asignación masiva? <span class="badge bg-warning text-dark">v1.2</span>',
         'Desde un parte diario, el botón <em>Asignación masiva</em> permite dar de alta a varias personas '
         'de una misma empresa a la vez, con las mismas horas, partida y asunto. Cada persona se valida '
         'individualmente (mes cerrado, límite de horas): las que no cumplan quedan bloqueadas y el resto '
         'se crean con normalidad.'),
        ('¿Qué significa finalizar una obra? <span class="badge bg-warning text-dark">v1.2</span>',
         'Desde <em>Estado de obra</em> puedes finalizar una obra cuando todos sus mensuales estén cerrados. '
         'Una obra finalizada queda congelada: no se pueden crear ni editar partes diarios, no se pueden '
         'crear ni reabrir mensuales, y la documentación pasa a solo lectura. Se puede reactivar en '
         'cualquier momento, pero los mensuales cerrados siguen cerrados hasta que los reabras a mano.'),
        ('¿Dónde se guarda la documentación de una obra? <span class="badge bg-warning text-dark">v1.2</span>',
         'En <em>Documentación</em> (icono de carpeta en la ficha de obra) puedes crear carpetas por partida '
         'y subir archivos (planos, fotos, PDFs...). Si borras una partida, sus documentos no se pierden: '
         'se archivan automáticamente y siguen siendo descargables desde la sección "Documentación archivada".'),
        ('¿Qué se registra en la auditoría? <span class="badge bg-warning text-dark">v1.2</span>',
         'En <em>Estado de obra</em> hay un panel "Actividad administrativa" con el histórico de acciones '
         'importantes: cerrar/reactivar obra, cerrar/reabrir mensuales y archivado de documentación al '
         'borrar una partida. Si el registro de un evento falla por algún motivo, la acción principal '
         '(cerrar el mes, etc.) se completa igualmente: la auditoría nunca bloquea el trabajo.'),
    ]
    return render_template_string(BASE + r"""
{% block af %}hi{% endblock %}{% block title %}FAQ{% endblock %}
{% block content %}
<h2 class="h4 mb-3"><i class="bi bi-question-circle"></i> Preguntas frecuentes</h2>
<div class="accordion" id="faq">
{% for q,a in preguntas %}
<div class="accordion-item border-secondary">
  <h2 class="accordion-header">
    <button class="accordion-button collapsed bg-dark text-light py-2" type="button"
            data-bs-toggle="collapse" data-bs-target="#fq{{ loop.index }}">
      {{ q }}
    </button>
  </h2>
  <div id="fq{{ loop.index }}" class="accordion-collapse collapse" data-bs-parent="#faq">
    <div class="accordion-body text-muted small">{{ a|safe }}</div>
  </div>
</div>
{% endfor %}
</div>
{% endblock %}
""", preguntas=preguntas)

# -- MAIN --
if __name__ == '__main__':
    with app.app_context():
        _init_if_needed()
    app.run(debug=False, host='127.0.0.1', port=5000)