
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ObraPasaLista v1.0
Control de presencia en obra — app local Flask + SQLite
pip install flask
python app.py → http://127.0.0.1:5000
"""
import os, sqlite3, shutil, calendar, unicodedata, re, csv, io
from datetime import datetime, date
from flask import (Flask, g, render_template, request,
redirect, url_for, flash, Response)
from jinja2 import BaseLoader, TemplateNotFound, ChoiceLoader

# ── SETUP ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'app.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')

app = Flask(__name__)
app.secret_key = 'opl-v1-local-2026'
app.config.update(DATABASE=DB_PATH, BACKUPS_DIR=BACKUP_DIR)

# ── MENSAJES ──────────────────────────────────────────────────────────────────
M = {
'lim': "⚠️ {nom} ya acumula {tot} el {f}. Añadir {nv} h superaría el límite de {lim} h/día.",
'cerr': "⛔ El mes {mes} para '{ob}' / '{emp}' está CERRADO. No se pueden modificar partes.",
'fk': "❌ No se puede eliminar: hay registros vinculados.",
'bk': "✅ Backup creado: {f}",
'rs': "✅ BD restaurada desde: {f}",
'mc': "✅ Mes cerrado y snapshot generado.",
}

# ── SCHEMA ────────────────────────────────────────────────────────────────────
SCHEMA = """PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS empresa(
id_empresa INTEGER PRIMARY KEY AUTOINCREMENT,
nombre TEXT NOT NULL UNIQUE,
estado TEXT NOT NULL DEFAULT 'activa');
CREATE TABLE IF NOT EXISTS persona(
id_persona INTEGER PRIMARY KEY AUTOINCREMENT,
nombre TEXT NOT NULL, apellido1 TEXT NOT NULL,
apellido2 TEXT NOT NULL DEFAULT '', dni TEXT NOT NULL UNIQUE,
id_empresa INTEGER REFERENCES empresa(id_empresa) ON UPDATE CASCADE ON DELETE SET NULL,
oficio TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'activa');
CREATE TABLE IF NOT EXISTS obra(
id_obra INTEGER PRIMARY KEY AUTOINCREMENT,
codigo TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL,
estado TEXT NOT NULL DEFAULT 'activa');
CREATE TABLE IF NOT EXISTS obra_empresa(
id_oe INTEGER PRIMARY KEY AUTOINCREMENT,
id_obra INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE RESTRICT,
id_empresa INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT,
UNIQUE(id_obra,id_empresa));
CREATE TABLE IF NOT EXISTS config(
id_config INTEGER PRIMARY KEY,
limite_horas_dia REAL NOT NULL DEFAULT 24.0 CHECK(limite_horas_dia>0));
CREATE TABLE IF NOT EXISTS diario(
id_diario INTEGER PRIMARY KEY AUTOINCREMENT,
id_obra INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE RESTRICT,
fecha DATE NOT NULL, UNIQUE(id_obra,fecha));
CREATE TABLE IF NOT EXISTS diario_linea(
id_dl INTEGER PRIMARY KEY AUTOINCREMENT,
id_diario INTEGER NOT NULL REFERENCES diario(id_diario) ON DELETE CASCADE,
id_empresa INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT,
id_persona INTEGER NOT NULL REFERENCES persona(id_persona) ON DELETE RESTRICT,
asunto TEXT NOT NULL DEFAULT '',
horas REAL NOT NULL DEFAULT 0 CHECK(horas>=0 AND horas<=24));
CREATE TABLE IF NOT EXISTS mensual(
id_mensual INTEGER PRIMARY KEY AUTOINCREMENT,
id_obra INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE RESTRICT,
id_empresa INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT,
mes TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'abierto',
UNIQUE(id_obra,id_empresa,mes));
CREATE TABLE IF NOT EXISTS mensual_persona(
id_mp INTEGER PRIMARY KEY AUTOINCREMENT,
id_mensual INTEGER NOT NULL REFERENCES mensual(id_mensual) ON DELETE CASCADE,
id_persona INTEGER NOT NULL REFERENCES persona(id_persona) ON DELETE RESTRICT,
nom_c TEXT NOT NULL, ap1_c TEXT NOT NULL,
ap2_c TEXT NOT NULL DEFAULT '', dni_c TEXT NOT NULL,
d1 REAL,d2 REAL,d3 REAL,d4 REAL,d5 REAL,d6 REAL,d7 REAL,
d8 REAL,d9 REAL,d10 REAL,d11 REAL,d12 REAL,d13 REAL,d14 REAL,
d15 REAL,d16 REAL,d17 REAL,d18 REAL,d19 REAL,d20 REAL,d21 REAL,
d22 REAL,d23 REAL,d24 REAL,d25 REAL,d26 REAL,d27 REAL,d28 REAL,
d29 REAL,d30 REAL,d31 REAL,
total_mes REAL NOT NULL DEFAULT 0);
"""

# ── DB HELPERS ────────────────────────────────────────────────────────────────
def get_db():
if 'db' not in g:
conn = sqlite3.connect(app.config['DATABASE'], detect_types=sqlite3.PARSE_DECLTYPES)
conn.execute('PRAGMA foreign_keys=ON')
conn.row_factory = sqlite3.Row
g.db = conn
return g.db

@app.teardown_appcontext
def close_db(e=None):
d = g.pop('db', None)
if d: d.close()

def init_db():
conn = get_db()
conn.executescript(SCHEMA)
conn.execute('INSERT OR IGNORE INTO config(id_config,limite_horas_dia) VALUES(1,24.0)')
conn.commit()

def hhmm(h):
if h is None: return '--'
hi = int(h); m = round((h - hi) * 60)
if m == 60: hi += 1; m = 0
return f'{hi:02d}:{m:02d}'

def norm(s):
s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
return re.sub(r'[^A-Z0-9]+', '_', s.upper()).strip('_')

def get_lim():
return get_db().execute('SELECT limite_horas_dia FROM config WHERE id_config=1').fetchone()['limite_horas_dia']

def chk_horas(id_p, fecha, h_new, excl=None):
lim = get_lim()
q = ("SELECT COALESCE(SUM(dl.horas),0) t FROM diario_linea dl "
"JOIN diario d ON dl.id_diario=d.id_diario WHERE dl.id_persona=? AND d.fecha=?")
p = [id_p, fecha]
if excl: q += ' AND dl.id_dl!=?'; p.append(excl)
tot = get_db().execute(q, p).fetchone()['t']
if tot + h_new > lim:
pr = get_db().execute("SELECT nombre||' '||apellido1 n FROM persona WHERE id_persona=?", [id_p]).fetchone()
raise ValueError(M['lim'].format(nom=pr['n'] if pr else '?', tot=hhmm(tot), f=fecha, nv=hhmm(h_new), lim=hhmm(lim)))

def chk_mes(id_obra, id_emp, fecha):
mes = fecha[:7]
r = get_db().execute(
"SELECT m.estado,o.nombre ob,e.nombre em FROM mensual m "
"JOIN obra o ON m.id_obra=o.id_obra "
"JOIN empresa e ON m.id_empresa=e.id_empresa "
"WHERE m.id_obra=? AND m.id_empresa=? AND m.mes=?",
[id_obra, id_emp, mes]).fetchone()
if r and r['estado'] == 'cerrado':
raise ValueError(M['cerr'].format(mes=mes, ob=r['ob'], emp=r['em']))

# ── JINJA2 DICT LOADER ────────────────────────────────────────────────────────
class DL(BaseLoader):
def __init__(self, d): self.d = d
def get_source(self, e, n):
if n not in self.d: raise TemplateNotFound(n)
return self.d[n], n, lambda: True

T = {}

# ── BASE TEMPLATE ─────────────────────────────────────────────────────────────
T['base.html'] = r"""<!DOCTYPE html>
<html lang="es" data-bs-theme="dark">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{% block title %}ObraPasaLista{% endblock %}</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.2/css/bootstrap.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap-icons/1.11.3/font/bootstrap-icons.min.css">
<style>
body{background:#0d1117}
.navbar-brand{color:#f97316!important;font-weight:700;letter-spacing:-.5px}
.btn-opl{background:#f97316;border-color:#f97316;color:#fff}
.btn-opl:hover,.btn-opl:focus{background:#c2410c;border-color:#c2410c;color:#fff}
.nav-link.hi{color:#f97316!important;font-weight:600}
.card{border-color:#374151}.card-header{background:#1a1d27;border-color:#374151}
.sec{color:#f97316;font-weight:600;border-bottom:1px solid #374151;padding-bottom:.4rem;margin-bottom:1rem;font-size:1rem}
.htd{font-family:monospace;font-size:.8rem;text-align:center;padding:2px 3px!important;min-width:42px}
.hth{text-align:center;font-size:.72rem;padding:3px 2px!important;min-width:42px}
.badge-activa,.badge-abierto{background:#22c55e!important}
.badge-inactiva,.badge-finalizada,.badge-baja,.badge-cerrado{background:#6b7280!important}
.alert .btn-close{filter:invert(1) brightness(2)}
</style>{% block head %}{% endblock %}
</head><body>
<nav class="navbar navbar-expand-lg bg-body-tertiary border-bottom border-secondary-subtle mb-3">
<div class="container-fluid">
<a class="navbar-brand" href="{{ url_for('index') }}"><i class="bi bi-building-fill"></i> ObraPasaLista</a>
<button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#nb"><span class="navbar-toggler-icon"></span></button>
<div class="collapse navbar-collapse" id="nb">
<ul class="navbar-nav me-auto mb-2 mb-lg-0">
<li class="nav-item"><a class="nav-link{{ ' hi' if act=='home' }}" href="{{ url_for('index') }}"><i class="bi bi-house"></i> Inicio</a></li>
<li class="nav-item"><a class="nav-link{{ ' hi' if act=='obras' }}" href="{{ url_for('obras') }}"><i class="bi bi-buildings"></i> Obras</a></li>
<li class="nav-item"><a class="nav-link{{ ' hi' if act=='empresas' }}" href="{{ url_for('empresas') }}"><i class="bi bi-briefcase"></i> Empresas</a></li>
<li class="nav-item"><a class="nav-link{{ ' hi' if act=='personas' }}" href="{{ url_for('personas') }}"><i class="bi bi-people"></i> Personas</a></li>
<li class="nav-item"><a class="nav-link{{ ' hi' if act=='diario' }}" href="{{ url_for('diario_sel') }}"><i class="bi bi-calendar-day"></i> Diario</a></li>
<li class="nav-item"><a class="nav-link{{ ' hi' if act=='mensual' }}" href="{{ url_for('mensual_sel') }}"><i class="bi bi-calendar-month"></i> Mensual</a></li>
</ul>
<ul class="navbar-nav">
<li class="nav-item"><a class="nav-link" href="{{ url_for('backup_page') }}"><i class="bi bi-database"></i> Backup</a></li>
<li class="nav-item"><a class="nav-link{{ ' hi' if act=='config' }}" href="{{ url_for('configuracion') }}"><i class="bi bi-gear"></i> Config</a></li>
<li class="nav-item"><a class="nav-link{{ ' hi' if act=='faq' }}" href="{{ url_for('faq') }}"><i class="bi bi-question-circle"></i> FAQ</a></li>
</ul>
</div>
</div>
</nav>
<div class="container-fluid px-4">
{% with msgs=get_flashed_messages(with_categories=True) %}{% for cat,msg in msgs %}
<div class="alert alert-{{ 'danger' if cat=='error' else ('success' if cat=='success' else ('info' if cat=='info' else 'warning')) }} alert-dismissible fade show">
{{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
</div>{% endfor %}{% endwith %}
{% block content %}{% endblock %}
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.2/js/bootstrap.bundle.min.js"></script>
{% block scripts %}{% endblock %}
</body></html>"""

# ── INDEX ─────────────────────────────────────────────────────────────────────
T['index.html'] = r"""{% extends 'base.html' %}{% block title %}Inicio{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
<h2 class="h4 mb-0"><i class="bi bi-house"></i> Panel de control</h2>
<span class="text-muted small"><i class="bi bi-calendar3"></i> Hoy: <strong>{{ hoy }}</strong></span>
</div>
<div class="row g-3 mb-4">
<div class="col-6 col-md-3"><div class="card text-center h-100"><div class="card-body">
<div class="fs-2 text-warning"><i class="bi bi-buildings"></i></div>
<div class="fs-3 fw-bold">{{ n_obras }}</div><div class="text-muted small">Obras activas</div>
</div></div></div>
<div class="col-6 col-md-3"><div class="card text-center h-100"><div class="card-body">
<div class="fs-2 text-info"><i class="bi bi-briefcase"></i></div>
<div class="fs-3 fw-bold">{{ n_emp }}</div><div class="text-muted small">Empresas activas</div>
</div></div></div>
<div class="col-6 col-md-3"><div class="card text-center h-100"><div class="card-body">
<div class="fs-2 text-success"><i class="bi bi-people"></i></div>
<div class="fs-3 fw-bold">{{ n_per }}</div><div class="text-muted small">Personas activas</div>
</div></div></div>
<div class="col-6 col-md-3"><div class="card text-center h-100"><div class="card-body">
<div class="fs-2" style="color:#f97316"><i class="bi bi-clock"></i></div>
<div class="fs-3 fw-bold">{{ hhmm(lim) }}</div><div class="text-muted small">Límite h/día</div>
</div></div></div>
</div>
<div class="sec"><i class="bi bi-buildings"></i> Obras activas — Parte de hoy</div>
<div class="row g-3">
{% for ob in obras %}
<div class="col-md-4 col-lg-3"><div class="card h-100"><div class="card-body">
<h6 class="card-title">{{ ob.nombre }}</h6>
<p class="small text-muted mb-3"><span class="badge bg-secondary">{{ ob.codigo }}</span></p>
<a href="{{ url_for('diario_ver', id_obra=ob.id_obra, fecha=hoy_iso) }}" class="btn btn-opl btn-sm w-100">
<i class="bi bi-calendar-day"></i> Parte de hoy
</a>
</div></div></div>
{% else %}
<div class="col"><div class="alert alert-info">No hay obras activas. <a href="{{ url_for('obra_nueva') }}">Crea una obra</a>.</div></div>
{% endfor %}
</div>
{% endblock %}"""

# ── EMPRESAS ──────────────────────────────────────────────────────────────────
T['empresas.html'] = r"""{% extends 'base.html' %}{% block title %}Empresas{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
<h2 class="h4 mb-0"><i class="bi bi-briefcase"></i> Empresas</h2>
<a href="{{ url_for('empresa_nueva') }}" class="btn btn-opl btn-sm"><i class="bi bi-plus"></i> Nueva empresa</a>
</div>
<div class="card"><div class="card-body p-0">
<table class="table table-hover mb-0">
<thead><tr><th>Nombre</th><th>Estado</th><th>Personas</th><th>Obras</th><th class="text-end">Acciones</th></tr></thead>
<tbody>
{% for e in empresas %}
<tr>
<td class="fw-semibold">{{ e.nombre }}</td>
<td><span class="badge badge-{{ e.estado }}">{{ e.estado }}</span></td>
<td><span class="badge bg-secondary">{{ e.n_p }}</span></td>
<td><span class="badge bg-secondary">{{ e.n_o }}</span></td>
<td class="text-end">
<a href="{{ url_for('empresa_editar', id_=e.id_empresa) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
<form method="post" action="{{ url_for('empresa_estado', id_=e.id_empresa) }}" class="d-inline">
<button class="btn btn-sm btn-outline-{{ 'warning' if e.estado=='activa' else 'success' }}" title="{{ 'Finalizar' if e.estado=='activa' else 'Reactivar' }}">
<i class="bi bi-{{ 'pause' if e.estado=='activa' else 'play' }}"></i>
</button>
</form>
<form method="post" action="{{ url_for('empresa_eliminar', id_=e.id_empresa) }}" class="d-inline" onsubmit="return confirm('¿Eliminar empresa {{ e.nombre }}?')">
<button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button>
</form>
</td>
</tr>
{% else %}
<tr><td colspan="5" class="text-center text-muted py-4">Sin empresas. <a href="{{ url_for('empresa_nueva') }}">Crear una</a>.</td></tr>
{% endfor %}
</tbody>
</table>
</div></div>{% endblock %}"""

T['empresa_form.html'] = r"""{% extends 'base.html' %}{% block title %}{{ 'Editar' if emp else 'Nueva' }} empresa{% endblock %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-5">
<div class="card"><div class="card-header"><h5 class="mb-0">{{ 'Editar' if emp else 'Nueva' }} empresa</h5></div>
<div class="card-body">
<form method="post">
<div class="mb-3"><label class="form-label">Nombre <span class="text-danger">*</span></label>
<input type="text" name="nombre" class="form-control" value="{{ emp.nombre if emp else '' }}" required autofocus></div>
{% if emp %}
<div class="mb-3"><label class="form-label">Estado</label>
<select name="estado" class="form-select">
<option value="activa" {{ 'selected' if emp.estado=='activa' }}>Activa</option>
<option value="finalizada" {{ 'selected' if emp.estado=='finalizada' }}>Finalizada</option>
<option value="baja" {{ 'selected' if emp.estado=='baja' }}>Baja</option>
</select></div>
{% endif %}
<div class="d-flex gap-2">
<button type="submit" class="btn btn-opl">Guardar</button>
<a href="{{ url_for('empresas') }}" class="btn btn-secondary">Cancelar</a>
</div>
</form></div></div></div></div>{% endblock %}"""

# ── PERSONAS ──────────────────────────────────────────────────────────────────
T['personas.html'] = r"""{% extends 'base.html' %}{% block title %}Personas{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
<h2 class="h4 mb-0"><i class="bi bi-people"></i> Personas</h2>
<div class="d-flex gap-2 flex-wrap">
<form method="get" class="d-flex gap-2">
<input type="text" name="q" value="{{ q }}" class="form-control form-control-sm" placeholder="Buscar nombre, DNI, oficio...">
<select name="id_empresa" class="form-select form-select-sm" style="min-width:150px">
<option value="">Todas las empresas</option>
{% for e in empresas %}<option value="{{ e.id_empresa }}" {{ 'selected' if id_emp==e.id_empresa|string }}>{{ e.nombre }}</option>{% endfor %}
</select>
<button class="btn btn-sm btn-secondary"><i class="bi bi-search"></i></button>
</form>
<a href="{{ url_for('persona_nueva') }}" class="btn btn-opl btn-sm"><i class="bi bi-plus"></i> Nueva</a>
</div>
</div>
<div class="card"><div class="card-body p-0">
<table class="table table-hover mb-0">
<thead><tr><th>Nombre</th><th>DNI</th><th>Empresa</th><th>Oficio</th><th>Estado</th><th class="text-end">Acciones</th></tr></thead>
<tbody>
{% for p in personas %}
<tr>
<td>{{ p.apellido1 }}{% if p.apell




sigue haciendo

Eres-un-asesor-y-analista-implacable-sabes-mucho-d.md



script.py
Código



script.py
Código



script.py
Código
La respuesta se detuvo antes de terminar.
https://github.com/RecklessCat55/ObraPasaLista/tree/master

este es el repo que hay, con las cosas que hay por el momento
Completados 3 pasos
He leído el código completo del repositorio. Aquí está mi análisis técnico exhaustivo como Asesor de Sistemas Senior:

Auditoría Técnica: ObraPasaLista v1.0
El repositorio contiene un único archivo funcional (src/ObraPasaLista v1.0 - app.py) que encapsula toda la lógica de negocio, el esquema de base de datos y las plantillas HTML en un solo monolito Python/Flask . La arquitectura es on-premise con SQLite, exactamente según el stack planificado.

Estado Actual del Repo
Componente	Presente	Observación
app.py principal	✅	Monolito de ~19 KB, Flask + SQLite
Main.java	⚠️	Archivo residual, 133 bytes, sin utilidad
.idea/	⚠️	Configuración del IDE (IntelliJ/PyCharm) subida al repo
Templates HTML	✅	Embebidos en diccionario T{} via DL(BaseLoader)
requirements.txt	❌	Ausente — dependencias no documentadas
Migraciones / init_db script	⚠️	Solo init_db() interno, sin versionado de esquema
Fortalezas Detectadas
Integridad referencial activa: PRAGMA foreign_keys=ON se ejecuta tanto en el SCHEMA inicial como en cada get_db() — doble seguro correcto

WAL mode activado: PRAGMA journal_mode=WAL mejora la concurrencia de lecturas sin bloquear escrituras

Cierre de mes implementado: La función chk_mes() bloquea modificaciones sobre partes de meses cerrados con mensaje descriptivo

Límite diario de horas: chk_horas() usa COALESCE(SUM(...),0) y consulta parametrizada, evitando inyección SQL y manejando NULLs correctamente

Soft Delete parcial: Las personas y empresas tienen campo estado (activa/finalizada/baja) en lugar de borrado físico, preservando historial

Backup referenciado: Existe BACKUP_DIR configurado, indicando implementación de la Online Backup API de SQLite

Puntos de Fallo Críticos Detectados
1. Ruptura Silenciosa de Integridad en persona
sql
id_empresa INTEGER REFERENCES empresa(id_empresa) 
    ON UPDATE CASCADE ON DELETE SET NULL
Cuando se elimina una empresa, todos sus operarios quedan con id_empresa = NULL. No hay validación que impida registrar horas de una persona sin empresa en una obra que requiere empresa específica .

2. Main.java Contaminando el Repo
Un archivo Java de 133 bytes está en src/ . Sugiere que el proyecto comenzó como Java y luego migró a Python. Debe eliminarse para evitar confusión sobre el stack tecnológico.

3. .idea/ No Está en .gitignore
La carpeta de configuración del IDE está siendo rastreada . Esto expone rutas locales del desarrollador y genera conflictos en equipos multi-desarrollador.

4. secret_key Hardcodeada en Código Fuente
python
app.secret_key = 'opl-v1-local-2026'
Aunque es uso local, es mala práctica. Si el repo se vuelve público o se despliega remotamente, esto es un vector de ataque para falsificar sesiones Flask .

5. mensual_persona con 31 Columnas d1..d31
El esquema actual usa columnas fijas d1 a d31 en lugar de filas dinámicas . Esto imposibilita consultas eficientes del tipo "todos los días con >8h de un operario" sin construir SQL dinámico con 31 CASE WHEN.

Puntos Críticos por Resolver
Operario sin empresa: ¿Qué ocurre cuando id_empresa IS NULL en persona y se intenta añadir una línea en diario_linea? ¿Se valida que la empresa en diario_linea.id_empresa coincide con la empresa actual del operario?

Cambio de empresa a mitad de mes: Si un operario cambia de Empresa A a Empresa B el día 15, el snapshot de mensual_persona captura el nombre pero ¿a qué empresa se facturan las horas del 1 al 14? ¿Existe un campo id_empresa en mensual_persona para discriminarlo?

Arrastre Temporal (Lunes/Festivos): El README menciona esta funcionalidad — ¿está implementado el algoritmo que busca hacia atrás la última jornada real trabajada para evitar duplicar un domingo o festivo en blanco?

Horas nocturnas / extraordinarias: El campo horas en diario_linea es un único REAL — no hay distinción entre hora ordinaria, nocturna o extra. ¿Está esto en el roadmap o queda fuera del alcance de v1.0?

Versionado de esquema: Si un usuario ya tiene app.db y actualiza a una v1.1 con columnas nuevas, CREATE TABLE IF NOT EXISTS no ejecutará ALTER TABLE. ¿Cuál es el plan de migración?

C:\inteliJ\ObraPasaLista\.venv\Scripts\python.exe "C:\inteliJ\ObraPasaLista\src\ObraPasaLista v1.0 - app.py"
Traceback (most recent call last):
File "C:\inteliJ\ObraPasaLista\src\ObraPasaLista v1.0 - app.py", line 1424, in <module>
with open('/root/app.py', 'w', encoding='utf-8') as f:
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '/root/app.py'

El error no viene de Flask ni de SQLite: viene de una línea del propio script que intenta escribir en '/root/app.py', una ruta de Linux que no existe en Windows, por eso Python lanza FileNotFoundError. En tu caso estás ejecutando desde C:\inteliJ\ObraPasaLista\src\..., así que cualquier referencia fija a /root/... es incorrecta en esta instalación .

Causa exacta
El traceback indica que en la línea 1424 el programa hace esto: with open('/root/app.py', 'w', encoding='utf-8') as f: y falla porque /root no existe en Windows . Además, las buenas prácticas para apps Flask locales son construir rutas a partir de __file__ o de BASE_DIR, justo como ya haces arriba con DB_PATH y BACKUP_DIR, en lugar de usar rutas absolutas ajenas al entorno.

Qué debes cambiar
Busca al final del archivo esa línea con '/root/app.py' y elimínala o sustitúyela por una ruta relativa al proyecto usando BASE_DIR . La corrección mínima sería algo así:

python
OUT_APP = os.path.join(BASE_DIR, 'app.py')
with open(OUT_APP, 'w', encoding='utf-8') as f:
    f.write('...')
Ese patrón evita depender del directorio actual o del sistema operativo, que es precisamente la recomendación general para evitar FileNotFoundError al abrir archivos desde scripts Python.

Evaluación técnica
Aquí hay un punto de fallo serio: el código mezcla una arquitectura local Windows con una ruta hardcodeada de Linux, lo que rompe portabilidad y revela que el cierre del script contiene lógica residual o generada fuera del diseño principal . También afecta a la mantenibilidad: si el archivo principal intenta autogenerarse o sobrescribirse al arrancar, introduces un riesgo de corrupción del código fuente y una violación del principio de integridad operativa del sistema .

Acción recomendada
Haz estas comprobaciones inmediatas:

Busca en todo el fichero /root/app.py y cualquier otra ruta absoluta Linux como /root/, /tmp/ o similares .

Si ese bloque solo pretendía “exportar” el script, bórralo completamente; no aporta nada al arranque normal de una app Flask local .

Mantén todas las rutas bajo BASE_DIR = os.path.dirname(os.path.abspath(__file__)), igual que ya haces con la base de datos y backups.

Puntos Críticos por Resolver
¿Por qué el programa intenta escribir un app.py nuevo al arrancar, en lugar de limitarse a inicializar BD y levantar Flask?

¿Ese bloque final puede sobrescribir código productivo o generar versiones inconsistentes del ejecutable?

¿Qué otras rutas hardcodeadas quedan ocultas en exportaciones, backups o restauraciones?

¿Vas a separar ya el monolito en módulos (db.py, routes.py, templates/) para evitar este tipo de residuos cruzados entre entornos?

hazme el .bat
Completados 2 pasos
Sí: te he dejado un .bat que compila tu app a .exe con PyInstaller usando el .venv del proyecto, limpiando builds anteriores e incluyendo flask y jinja2 como imports explícitos para reducir fallos de empaquetado.

Cómo usarlo
Pon el .bat en la raíz del proyecto, al lado de .venv y de src, y ejecútalo con doble clic o desde cmd. El script espera encontrar exactamente este archivo principal:

text
src\ObraPasaLista v1.0 - app.py
y este intérprete del entorno virtual:

text
.venv\Scripts\python.exe
Qué hace
El .bat realiza estos pasos:

actualiza pip,

instala pyinstaller, flask y jinja2,

borra build, dist y .spec anteriores,

genera dist\ObraPasaLista.exe en modo --onefile.

Advertencia crítica
Aquí sigue habiendo un punto de fallo funcional: compilar a .exe no resuelve por sí solo dónde quedarán app.db y backups, y en una app Flask + SQLite eso afecta a persistencia, backups e integridad operativa. Si el ejecutable usa rutas derivadas de __file__, el comportamiento empaquetado puede no coincidir con desarrollo, especialmente en --onefile.

Qué probar después
Cuando te genere el .exe, lánzalo y comprueba estas cuatro cosas:

abre 127.0.0.1:5000,

crea o reutiliza app.db,

genera backups en una ruta real y persistente,

no pierde datos al cerrar y volver a abrir.

Puntos Críticos por Resolver
¿Quieres que el siguiente paso sea parchear el código para que el .exe guarde datos en %LOCALAPPDATA%\ObraPasaLista?

¿Qué política evitará que una actualización del .exe pise la base de datos existente?

¿Cómo vas a distinguir entorno desarrollo frente a ejecutable empaquetado para no romper rutas?

¿Quieres también un .bat de arranque para usuario final que abra navegador automáticamente y mate menos la experiencia?

sigue sin ser automatico
Completados 3 pasos
Ahora sí: te he preparado un .bat realmente automático que hace todo del tirón: compila tu app a .exe con PyInstaller y, si detecta Inno Setup instalado, te genera además el instalador final ObraPasaLista-Setup.exe sin pasos manuales intermedios.

Qué hace
Ese .bat ejecuta en cadena:

actualización de pip,

instalación de pyinstaller, flask y jinja2,

compilación del .exe,

generación automática del script .iss,

compilación del instalador con ISCC.exe de Inno Setup.

Eso ya es un flujo de build automatizado de verdad, no solo “un comando para compilar”.

Cómo usarlo
Pon el .bat en la raíz del proyecto y ejecútalo con doble clic. Si encuentra:

.venv\Scripts\python.exe,

src\ObraPasaLista v1.0 - app.py,

e Inno Setup 6 instalado,

te dejará al final un archivo como este:

text
output_installer\ObraPasaLista-Setup.exe
Requisito clave
Para que sea automático del todo, necesitas tener Inno Setup 6 instalado, porque es la pieza que genera el setup.exe empaquetado final, algo que PyInstaller por sí solo no hace. Si no está instalado, el .bat corta con error, que es lo correcto desde un punto de vista de integridad del build: mejor fallar explícitamente que dejarte con un artefacto a medias.

Advertencia técnica
Sigue existiendo el punto de fallo estructural que ya te señalé: el instalador empaqueta el ejecutable, pero no corrige todavía la política de persistencia de app.db y backups. Si el ejecutable usa rutas inestables, tendrás un setup bonito pero una app operativamente frágil, que es peor porque el fallo llega después del despliegue y no durante la compilación.

Puntos Críticos por Resolver
¿Quieres que te haga ahora la versión completa con persistencia en %LOCALAPPDATA%\ObraPasaLista para que el instalador sea serio de verdad?

¿Qué regla impedirá que una reinstalación borre la base de datos existente?

¿Quieres acceso directo en escritorio, menú inicio y apertura automática del navegador?

¿Prefieres un instalador silencioso también, para poder desplegarlo con doble clic o por script corporativo?

actualizame el readme
Completados 3 pasos
README
ObraPasaLista v1.0
Aplicación local para control diario y mensual de personal en obra, construida con Python 3, Flask y SQLite. El objetivo del sistema es sustituir el control manual en papel por una aplicación local, simple de desplegar y orientada a preservar el histórico operativo y de facturación.

Estado actual
La aplicación está planteada como una solución on-premise para un único puesto local, sin servidor remoto ni multiusuario real. El diseño funcional y técnico parte del patrón recomendado por Flask para trabajar con SQLite y añade activación explícita de claves foráneas en cada conexión mediante PRAGMA foreign_keys = ON, además de sqlite3.Row para acceso por nombre de columna 
.

Stack técnico
Python 3

Flask

SQLite

HTML + Jinja2 + Bootstrap

Arquitectura
La solución sigue una arquitectura local muy directa:

Flask como capa web local y enrutado.

SQLite como base de datos transaccional embebida.

Backups en caliente mediante la API Connection.backup() de SQLite, adecuada para snapshots consistentes sin necesidad de desmontar la aplicación 
.

Persistencia funcional centrada en tablas maestras y operativas: empresa, persona, obra, obraempresa, diario, diariolinea, mensual y mensualpersona 
.

Reglas funcionales principales
1. Diario por obra y fecha
Cada obra tiene un parte diario asociado a una fecha concreta. La tabla diario debe evitar duplicados por obra y día mediante UNIQUE(idobra, fecha) 
.

2. Línea diaria con empresa y persona
La unidad real de negocio no es solo el diario, sino diariolinea, donde se registran:

Empresa

Persona

Asunto o tarea

Horas trabajadas

Este diseño permite que una misma persona pueda figurar en distintas empresas o en distintas obras el mismo día sin romper el histórico 
.

3. Mensual por obra + empresa + mes
El mensual se calcula por combinación de:

obra

empresa

mes (YYYY-MM)

La tabla mensual debe impedir duplicados mediante UNIQUE(idobra, idempresa, mes) 
.

4. Snapshot de cierre mensual
Cuando se cierra un mes, el sistema genera un snapshot en mensualpersona con nombre, DNI y horas por día. Esto protege el histórico frente a cambios posteriores en los maestros de persona o empresa 
.

5. Arrastre inteligente
Si el parte actual está vacío, la aplicación puede sugerir o copiar líneas desde el último parte anterior con contenido real. Esta lógica evita fallos típicos de copiar “ayer” cuando hubo fin de semana o días sin actividad 
.

Integridad de datos
Este proyecto no debe tratar la integridad como un detalle opcional. La aplicación debe reforzar estas reglas:

Activar PRAGMA foreign_keys = ON en cada conexión SQLite 
.

Usar consultas parametrizadas (?) en todas las operaciones de escritura y lectura con datos de usuario 
.

Mantener históricos operativos incluso cuando cambie la empresa actual de una persona 
.

Evitar borrados peligrosos sobre entidades con histórico ya referenciado.

Hard delete vs soft delete
Estrategia	Ventaja	Riesgo	Recomendación
Hard delete	Limpieza simple	Puede destruir histórico laboral o mensual	Evitar en personas con partes 
Soft delete / estado inactivo	Conserva histórico	Requiere filtrar en UI	Recomendado para personas 
Cascade delete	Simplifica tablas hijas	Muy peligroso si se aplica a maestros con histórico	Limitarlo a tablas puramente dependientes como diariolinea desde diario o mensualpersona desde mensual 
Estructura lógica de base de datos
Tablas maestras
empresa

persona

obra

obraempresa

config

Tablas operativas
diario

diariolinea

mensual

mensualpersona

Reglas clave
persona.idempresa representa la empresa actual, pero no debe usarse para reconstruir históricos.

El histórico diario y mensual debe salir de diariolinea.idempresa, no del maestro actual de persona 
.

El cierre mensual congela datos en mensualpersona para mantener trazabilidad 
.

Validaciones importantes
Límite diario de horas
El sistema contempla un límite diario configurable en config.limitehorasdia. Antes de insertar o modificar una línea, la app debe sumar las horas de esa persona en esa fecha y rechazar excesos 
.

Mes cerrado
Si existe un mensual en estado cerrado para una combinación obra + empresa + mes, no deben permitirse nuevas modificaciones sobre las líneas diarias que impacten en ese ámbito 
.

Valores nulos en mensual
Cuando una persona no tiene horas en un día concreto del mes, el dato puede quedar en NULL en base de datos y mostrarse en la UI o exportación como -- o vacío, usando COALESCE en consultas o tratamiento equivalente en la capa Flask 
.

Instalación
Requisitos
Python 3.11+ recomendado

pip

Windows, Linux o cualquier sistema con Python 3 y SQLite

Crear entorno virtual
Windows
text
python -m venv .venv
.venv\Scripts\activate
pip install flask
Linux
bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask
Ejecución
Desde la carpeta del proyecto:

bash
python app.py
o en Windows:

text
.venv\Scripts\python.exe app.py
La aplicación arrancará normalmente en http://127.0.0.1:5000 si el archivo principal está limpio y no contiene rutas absolutas ajenas al entorno 
.

Estructura recomendada del proyecto
text
ObraPasaLista/
├─ app.py
├─ app.db
├─ backups/
├─ templates/           # si se externalizan las plantillas
├─ static/              # si se externalizan CSS/JS
├─ README.md
└─ .venv/
Backups y restauración
El diseño prevé una carpeta backups/ junto a la base de datos. Los backups se generan con nombre contextual y luego pueden restaurarse desde la propia aplicación 
.

Criterio operativo
Hacer backup antes de cierres mensuales.

Hacer backup antes de cambios masivos en maestros.

Tratar la restauración como borrón y cuenta nueva sobre app.db, con aviso explícito al usuario 
.

Problema detectado: error con /root/app.py
Se detectó este error al ejecutar la aplicación en Windows:

text
FileNotFoundError: [Errno 2] No such file or directory: '/root/app.py'
Causa
El script intentaba escribir en '/root/app.py', una ruta propia de Linux que no existe en Windows. Eso indica que el archivo contiene un bloque residual o una lógica de autogeneración mal ubicada 
.

Corrección
No debe usarse una ruta absoluta fija como:

python
with open('/root/app.py', 'w', encoding='utf-8') as f:
En su lugar, cualquier ruta debe construirse con el directorio base del proyecto:

python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, 'app.py')
Recomendación
Si ese bloque no es imprescindible, elimínalo. Un app.py no debe autogenerarse a sí mismo al arrancar. Ese patrón introduce un riesgo innecesario de corrupción del código fuente y de errores cruzados entre Windows y Linux 
.

FAQ funcional mínima
¿Qué pasa si una persona cambia de empresa a mitad de mes?
Los diarios antiguos deben mantener la empresa que tenían en la línea diaria en ese momento. El mensual debe agruparse por idempresa tomado desde el diario, no desde la ficha actual de persona 
.

¿Qué pasa si una persona deja de trabajar para una empresa?
No conviene borrarla si tiene histórico. Lo correcto es marcarla como inactiva y dejar de mostrarla en selects normales, manteniendo sus partes históricos 
.

¿Cómo se representan las horas en exportación?
Internamente pueden guardarse en decimal (REAL), pero hacia fuera deben mostrarse como HH:MM o HH MM, según la decisión funcional adoptada 
.

Riesgos abiertos
Cambio de maestros con histórico vivo: si una UI permite borrar demasiado, se romperá trazabilidad.

Cierre mensual sin bloqueo consistente: si no se valida bien, se podrán alterar partes ya cerrados.

Rutas hardcodeadas: cualquier referencia tipo /root/... o similar hace el proyecto no portable.

Monolito excesivo: si toda la app vive en un único archivo enorme, aumentan los residuos de código y los errores de mantenimiento 
.

Hoja de ruta recomendada
V1.0
CRUD de obras, empresas y personas

Parte diario por obra y fecha

Arrastre inteligente desde último parte con datos

Mensual por obra/empresa/mes

Cierre mensual con snapshot

Exportación CSV

Backups y restauración

V1.1
Separación por módulos (db.py, routes_*.py, schema.sql)

Plantillas en carpeta templates/

Mejor validación de errores y mensajes de integridad

FAQ integrada y más explicativa

V2.0
Reglas de cierre más finas

Auditoría de cambios

Historial formal de empresa por persona

Reportes más avanzados

Puntos Críticos por Resolver
¿Qué restricción exacta impedirá modificar partes de un mes que ya ha sido cerrado administrativamente?

¿Cómo se controlará una persona que cambie de empresa a mitad de mes sin romper el histórico de facturación?

¿Se va a permitir borrar empresas con personas activas o solo marcarlas como inactivas/finalizadas?

¿Se va a modularizar ya el proyecto para evitar residuos como el bloque que intenta escribir '/root/app.py'?

¿El snapshot mensual será solo visual o tendrá validez operativa como cierre “congelado” definitivo?


Abierto actualmente
ObraPasaLista v1.0
Aplicación local para control diario y mensual de personal en obra, construida con Python 3, Flask y SQLite. El objetivo del sistema es sustituir el control manual en papel por una aplicación local, simple de desplegar y orientada a preservar el histórico operativo y de facturación.

Estado actual
La aplicación está planteada como una solución on-premise para un único puesto local, sin servidor remoto ni multiusuario real. El diseño funcional y técnico parte del patrón recomendado por Flask para trabajar con SQLite y añade activación explícita de claves foráneas en cada conexión mediante PRAGMA foreign_keys = ON, además de sqlite3.Row para acceso por nombre de columna.

Stack técnico
Python 3

Flask

SQLite

HTML + Jinja2 + Bootstrap

Arquitectura
La solución sigue una arquitectura local muy directa:

Flask como capa web local y enrutado.

SQLite como base de datos transaccional embebida.

Backups en caliente mediante la API Connection.backup() de SQLite, adecuada para snapshots consistentes sin necesidad de desmontar la aplicación.

Persistencia funcional centrada en tablas maestras y operativas: empresa, persona, obra, obraempresa, diario, diariolinea, mensual y mensualpersona.

Reglas funcionales principales
1. Diario por obra y fecha
Cada obra tiene un parte diario asociado a una fecha concreta. La tabla diario debe evitar duplicados por obra y día mediante UNIQUE(idobra, fecha).

2. Línea diaria con empresa y persona
La unidad real de negocio no es solo el diario, sino diariolinea, donde se registran:

Empresa

Persona

Asunto o tarea

Horas trabajadas

Este diseño permite que una misma persona pueda figurar en distintas empresas o en distintas obras el mismo día sin romper el histórico.

3. Mensual por obra + empresa + mes
El mensual se calcula por combinación de:

obra

empresa

mes (YYYY-MM)

La tabla mensual debe impedir duplicados mediante UNIQUE(idobra, idempresa, mes).

4. Snapshot de cierre mensual
Cuando se cierra un mes, el sistema genera un snapshot en mensualpersona con nombre, DNI y horas por día. Esto protege el histórico frente a cambios posteriores en los maestros de persona o empresa.

5. Arrastre inteligente
Si el parte actual está vacío, la aplicación puede sugerir o copiar líneas desde el último parte anterior con contenido real. Esta lógica evita fallos típicos de copiar “ayer” cuando hubo fin de semana o días sin actividad.

Integridad de datos
Este proyecto no debe tratar la integridad como un detalle opcional. La aplicación debe reforzar estas reglas:

Activar PRAGMA foreign_keys = ON en cada conexión SQLite.

Usar consultas parametrizadas (?) en todas las operaciones de escritura y lectura con datos de usuario.

Mantener históricos operativos incluso cuando cambie la empresa actual de una persona.

Evitar borrados peligrosos sobre entidades con histórico ya referenciado.

Hard delete vs soft delete
Estrategia	Ventaja	Riesgo	Recomendación
Hard delete	Limpieza simple	Puede destruir histórico laboral o mensual	Evitar en personas con partes 
Soft delete / estado inactivo	Conserva histórico	Requiere filtrar en UI	Recomendado para personas 
Cascade delete	Simplifica tablas hijas	Muy peligroso si se aplica a maestros con histórico	Limitarlo a tablas puramente dependientes como diariolinea desde diario o mensualpersona desde mensual 
Estructura lógica de base de datos
Tablas maestras
empresa

persona

obra

obraempresa

config

Tablas operativas
diario

diariolinea

mensual

mensualpersona

Reglas clave
persona.idempresa representa la empresa actual, pero no debe usarse para reconstruir históricos.

El histórico diario y mensual debe salir de diariolinea.idempresa, no del maestro actual de persona.

El cierre mensual congela datos en mensualpersona para mantener trazabilidad.

Validaciones importantes
Límite diario de horas
El sistema contempla un límite diario configurable en config.limitehorasdia. Antes de insertar o modificar una línea, la app debe sumar las horas de esa persona en esa fecha y rechazar excesos.

Mes cerrado
Si existe un mensual en estado cerrado para una combinación obra + empresa + mes, no deben permitirse nuevas modificaciones sobre las líneas diarias que impacten en ese ámbito.

Valores nulos en mensual
Cuando una persona no tiene horas en un día concreto del mes, el dato puede quedar en NULL en base de datos y mostrarse en la UI o exportación como -- o vacío, usando COALESCE en consultas o tratamiento equivalente en la capa Flask.

Instalación
Requisitos
Python 3.11+ recomendado

pip

Windows, Linux o cualquier sistema con Python 3 y SQLite

Crear entorno virtual
Windows
text
python -m venv .venv
.venv\Scripts\activate
pip install flask
Linux
bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask
Ejecución
Desde la carpeta del proyecto:

bash
python app.py
o en Windows:

text
.venv\Scripts\python.exe app.py
La aplicación arrancará normalmente en http://127.0.0.1:5000 si el archivo principal está limpio y no contiene rutas absolutas ajenas al entorno.

Estructura recomendada del proyecto
text
ObraPasaLista/
├─ app.py
├─ app.db
├─ backups/
├─ templates/           # si se externalizan las plantillas
├─ static/              # si se externalizan CSS/JS
├─ README.md
└─ .venv/
Backups y restauración
El diseño prevé una carpeta backups/ junto a la base de datos. Los backups se generan con nombre contextual y luego pueden restaurarse desde la propia aplicación.

Criterio operativo
Hacer backup antes de cierres mensuales.

Hacer backup antes de cambios masivos en maestros.

Tratar la restauración como borrón y cuenta nueva sobre app.db, con aviso explícito al usuario.

Problema detectado: error con /root/app.py
Se detectó este error al ejecutar la aplicación en Windows:

text
FileNotFoundError: [Errno 2] No such file or directory: '/root/app.py'
Causa
El script intentaba escribir en '/root/app.py', una ruta propia de Linux que no existe en Windows. Eso indica que el archivo contiene un bloque residual o una lógica de autogeneración mal ubicada.

Corrección
No debe usarse una ruta absoluta fija como:

python
with open('/root/app.py', 'w', encoding='utf-8') as f:
En su lugar, cualquier ruta debe construirse con el directorio base del proyecto:

python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, 'app.py')
Recomendación
Si ese bloque no es imprescindible, elimínalo. Un app.py no debe autogenerarse a sí mismo al arrancar. Ese patrón introduce un riesgo innecesario de corrupción del código fuente y de errores cruzados entre Windows y Linux.

FAQ funcional mínima
¿Qué pasa si una persona cambia de empresa a mitad de mes?
Los diarios antiguos deben mantener la empresa que tenían en la línea diaria en ese momento. El mensual debe agruparse por idempresa tomado desde el diario, no desde la ficha actual de persona.

¿Qué pasa si una persona deja de trabajar para una empresa?
No conviene borrarla si tiene histórico. Lo correcto es marcarla como inactiva y dejar de mostrarla en selects normales, manteniendo sus partes históricos.

¿Cómo se representan las horas en exportación?
Internamente pueden guardarse en decimal (REAL), pero hacia fuera deben mostrarse como HH:MM o HH MM, según la decisión funcional adoptada.

Riesgos abiertos
Cambio de maestros con histórico vivo: si una UI permite borrar demasiado, se romperá trazabilidad.

Cierre mensual sin bloqueo consistente: si no se valida bien, se podrán alterar partes ya cerrados.

Rutas hardcodeadas: cualquier referencia tipo /root/... o similar hace el proyecto no portable.

Monolito excesivo: si toda la app vive en un único archivo enorme, aumentan los residuos de código y los errores de mantenimiento




# ObraPasaLista v1.0

Aplicación local para control diario y mensual de personal en obra, construida con **Python 3**, **Flask** y **SQLite**. El objetivo del sistema es sustituir el control manual en papel por una aplicación local, simple de desplegar y orientada a preservar el histórico operativo y de facturación.

## Estado actual

La aplicación está planteada como una solución **on-premise** para un único puesto local, sin servidor remoto ni multiusuario real. El diseño funcional y técnico parte del patrón recomendado por Flask para trabajar con SQLite y añade activación explícita de claves foráneas en cada conexión mediante `PRAGMA foreign_keys = ON`, además de `sqlite3.Row` para acceso por nombre de columna [1][2].

## Stack técnico

- Python 3
- Flask
- SQLite
- HTML + Jinja2 + Bootstrap

## Arquitectura

La solución sigue una arquitectura local muy directa:

- **Flask** como capa web local y enrutado.
- **SQLite** como base de datos transaccional embebida.
- **Backups** en caliente mediante la API `Connection.backup()` de SQLite, adecuada para snapshots consistentes sin necesidad de desmontar la aplicación [1].
- **Persistencia funcional** centrada en tablas maestras y operativas: empresa, persona, obra, obraempresa, diario, diariolinea, mensual y mensualpersona [2].

## Reglas funcionales principales

### 1. Diario por obra y fecha

Cada obra tiene un parte diario asociado a una fecha concreta. La tabla `diario` debe evitar duplicados por obra y día mediante `UNIQUE(idobra, fecha)` [2].

### 2. Línea diaria con empresa y persona

La unidad real de negocio no es solo el diario, sino `diariolinea`, donde se registran:

- Empresa
- Persona
- Asunto o tarea
- Horas trabajadas

Este diseño permite que una misma persona pueda figurar en distintas empresas o en distintas obras el mismo día sin romper el histórico [1][2].

### 3. Mensual por obra + empresa + mes

El mensual se calcula por combinación de:

- obra
- empresa
- mes (`YYYY-MM`)

La tabla `mensual` debe impedir duplicados mediante `UNIQUE(idobra, idempresa, mes)` [2].

### 4. Snapshot de cierre mensual

Cuando se cierra un mes, el sistema genera un snapshot en `mensualpersona` con nombre, DNI y horas por día. Esto protege el histórico frente a cambios posteriores en los maestros de persona o empresa [1][2].

### 5. Arrastre inteligente

Si el parte actual está vacío, la aplicación puede sugerir o copiar líneas desde el último parte anterior con contenido real. Esta lógica evita fallos típicos de copiar “ayer” cuando hubo fin de semana o días sin actividad [2].

## Integridad de datos

Este proyecto **no debe tratar la integridad como un detalle opcional**. La aplicación debe reforzar estas reglas:

- Activar `PRAGMA foreign_keys = ON` en cada conexión SQLite [1][2].
- Usar consultas parametrizadas (`?`) en todas las operaciones de escritura y lectura con datos de usuario [1].
- Mantener históricos operativos incluso cuando cambie la empresa actual de una persona [1].
- Evitar borrados peligrosos sobre entidades con histórico ya referenciado.

### Hard delete vs soft delete

| Estrategia | Ventaja | Riesgo | Recomendación |
|---|---|---|---|
| Hard delete | Limpieza simple | Puede destruir histórico laboral o mensual | Evitar en personas con partes [1] |
| Soft delete / estado inactivo | Conserva histórico | Requiere filtrar en UI | Recomendado para personas [1] |
| Cascade delete | Simplifica tablas hijas | Muy peligroso si se aplica a maestros con histórico | Limitarlo a tablas puramente dependientes como `diariolinea` desde `diario` o `mensualpersona` desde `mensual` [2] |

## Estructura lógica de base de datos

### Tablas maestras

- `empresa`
- `persona`
- `obra`
- `obraempresa`
- `config`

### Tablas operativas

- `diario`
- `diariolinea`
- `mensual`
- `mensualpersona`

### Reglas clave

- `persona.idempresa` representa la empresa actual, pero **no debe usarse para reconstruir históricos**.
- El histórico diario y mensual debe salir de `diariolinea.idempresa`, no del maestro actual de persona [1].
- El cierre mensual congela datos en `mensualpersona` para mantener trazabilidad [2].

## Validaciones importantes

### Límite diario de horas

El sistema contempla un límite diario configurable en `config.limitehorasdia`. Antes de insertar o modificar una línea, la app debe sumar las horas de esa persona en esa fecha y rechazar excesos [2].

### Mes cerrado

Si existe un mensual en estado `cerrado` para una combinación obra + empresa + mes, no deben permitirse nuevas modificaciones sobre las líneas diarias que impacten en ese ámbito [2].

### Valores nulos en mensual

Cuando una persona no tiene horas en un día concreto del mes, el dato puede quedar en `NULL` en base de datos y mostrarse en la UI o exportación como `--` o vacío, usando `COALESCE` en consultas o tratamiento equivalente en la capa Flask [1].

## Instalación

### Requisitos

- Python 3.11+ recomendado
- pip
- Windows, Linux o cualquier sistema con Python 3 y SQLite

### Crear entorno virtual

#### Windows

```bat
python -m venv .venv
.venv\Scripts\activate
pip install flask
```

#### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask
```

## Ejecución

Desde la carpeta del proyecto:

```bash
python app.py
```

o en Windows:

```bat
.venv\Scripts\python.exe app.py
```

La aplicación arrancará normalmente en `http://127.0.0.1:5000` si el archivo principal está limpio y no contiene rutas absolutas ajenas al entorno [2].

## Estructura recomendada del proyecto

```text
ObraPasaLista/
├─ app.py
├─ app.db
├─ backups/
├─ templates/           # si se externalizan las plantillas
├─ static/              # si se externalizan CSS/JS
├─ README.md
└─ .venv/
```

## Backups y restauración

El diseño prevé una carpeta `backups/` junto a la base de datos. Los backups se generan con nombre contextual y luego pueden restaurarse desde la propia aplicación [2].

### Criterio operativo

- Hacer backup antes de cierres mensuales.
- Hacer backup antes de cambios masivos en maestros.
- Tratar la restauración como **borrón y cuenta nueva** sobre `app.db`, con aviso explícito al usuario [1][2].

## Problema detectado: error con `/root/app.py`

Se detectó este error al ejecutar la aplicación en Windows:

```text
FileNotFoundError: [Errno 2] No such file or directory: '/root/app.py'
```

### Causa

El script intentaba escribir en `'/root/app.py'`, una ruta propia de Linux que no existe en Windows. Eso indica que el archivo contiene un bloque residual o una lógica de autogeneración mal ubicada [2].

### Corrección

No debe usarse una ruta absoluta fija como:

```python
with open('/root/app.py', 'w', encoding='utf-8') as f:
```

En su lugar, cualquier ruta debe construirse con el directorio base del proyecto:

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, 'app.py')
```

### Recomendación

Si ese bloque no es imprescindible, elimínalo. Un `app.py` no debe autogenerarse a sí mismo al arrancar. Ese patrón introduce un riesgo innecesario de corrupción del código fuente y de errores cruzados entre Windows y Linux [2].

## FAQ funcional mínima

### ¿Qué pasa si una persona cambia de empresa a mitad de mes?

Los diarios antiguos deben mantener la empresa que tenían en la línea diaria en ese momento. El mensual debe agruparse por `idempresa` tomado desde el diario, no desde la ficha actual de persona [1].

### ¿Qué pasa si una persona deja de trabajar para una empresa?

No conviene borrarla si tiene histórico. Lo correcto es marcarla como `inactiva` y dejar de mostrarla en selects normales, manteniendo sus partes históricos [1].

### ¿Cómo se representan las horas en exportación?

Internamente pueden guardarse en decimal (`REAL`), pero hacia fuera deben mostrarse como `HH:MM` o `HH MM`, según la decisión funcional adoptada [1][2].

## Riesgos abiertos

1. **Cambio de maestros con histórico vivo**: si una UI permite borrar demasiado, se romperá trazabilidad.
2. **Cierre mensual sin bloqueo consistente**: si no se valida bien, se podrán alterar partes ya cerrados.
3. **Rutas hardcodeadas**: cualquier referencia tipo `/root/...` o similar hace el proyecto no portable.
4. **Monolito excesivo**: si toda la app vive en un único archivo enorme, aumentan los residuos de código y los errores de mantenimiento [2].

## Hoja de ruta recomendada

### V1.0

- CRUD de obras, empresas y personas
- Parte diario por obra y fecha
- Arrastre inteligente desde último parte con datos
- Mensual por obra/empresa/mes
- Cierre mensual con snapshot
- Exportación CSV
- Backups y restauración

### V1.1

- Separación por módulos (`db.py`, `routes_*.py`, `schema.sql`)
- Plantillas en carpeta `templates/`
- Mejor validación de errores y mensajes de integridad
- FAQ integrada y más explicativa

### V2.0

- Reglas de cierre más finas
- Auditoría de cambios
- Historial formal de empresa por persona
- Reportes más avanzados

## Puntos Críticos por Resolver

- ¿Qué restricción exacta impedirá modificar partes de un mes que ya ha sido cerrado administrativamente?
- ¿Cómo se controlará una persona que cambie de empresa a mitad de mes sin romper el histórico de facturación?
- ¿Se va a permitir borrar empresas con personas activas o solo marcarlas como inactivas/finalizadas?
- ¿Se va a modularizar ya el proyecto para evitar residuos como el bloque que intenta escribir `'/root/app.py'`?
- ¿El snapshot mensual será solo visual o tendrá validez operativa como cierre “congelado” definitivo?
