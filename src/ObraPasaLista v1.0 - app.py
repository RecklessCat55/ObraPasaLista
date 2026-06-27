#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ObraPasaLista v1.0
Control de presencia en obra — app local Flask + SQLite
pip install flask
python app.py  →  http://127.0.0.1:5000
"""
import os, sqlite3, shutil, calendar, unicodedata, re, csv, io
from datetime import datetime, date
from flask import (Flask, g, render_template, request,
                   redirect, url_for, flash, Response)
from jinja2 import BaseLoader, TemplateNotFound, ChoiceLoader

# ── SETUP ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, 'app.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')

app = Flask(__name__)
app.secret_key = 'opl-v1-local-2026'
app.config.update(DATABASE=DB_PATH, BACKUPS_DIR=BACKUP_DIR)

# ── MENSAJES ──────────────────────────────────────────────────────────────────
M = {
    'lim':  "⚠️ {nom} ya acumula {tot} el {f}. Añadir {nv} h superaría el límite de {lim} h/día.",
    'cerr': "⛔ El mes {mes} para '{ob}' / '{emp}' está CERRADO. No se pueden modificar partes.",
    'fk':   "❌ No se puede eliminar: hay registros vinculados.",
    'bk':   "✅ Backup creado: {f}",
    'rs':   "✅ BD restaurada desde: {f}",
    'mc':   "✅ Mes cerrado y snapshot generado.",
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
    <td>{{ p.apellido1 }}{% if p.apellido2 %} {{ p.apellido2 }}{% endif %}, {{ p.nombre }}</td>
    <td class="font-monospace small">{{ p.dni }}</td>
    <td>{{ p.empresa or '<span class="text-muted">—</span>'|safe }}</td>
    <td class="small text-muted">{{ p.oficio or '—' }}</td>
    <td><span class="badge badge-{{ p.estado }}">{{ p.estado }}</span></td>
    <td class="text-end">
      <a href="{{ url_for('persona_editar', id_=p.id_persona) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="post" action="{{ url_for('persona_estado', id_=p.id_persona) }}" class="d-inline">
        <button class="btn btn-sm btn-outline-{{ 'warning' if p.estado=='activa' else 'success' }}" title="{{ 'Inactivar' if p.estado=='activa' else 'Reactivar' }}">
          <i class="bi bi-{{ 'person-dash' if p.estado=='activa' else 'person-check' }}"></i>
        </button>
      </form>
      <form method="post" action="{{ url_for('persona_eliminar', id_=p.id_persona) }}" class="d-inline" onsubmit="return confirm('¿Eliminar a {{ p.nombre }} {{ p.apellido1 }}? Solo posible si no tiene partes.')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button>
      </form>
    </td>
  </tr>
  {% else %}
  <tr><td colspan="6" class="text-center text-muted py-4">Sin personas. <a href="{{ url_for('persona_nueva') }}">Crear una</a>.</td></tr>
  {% endfor %}
  </tbody>
</table>
</div></div>{% endblock %}"""

T['persona_form.html'] = r"""{% extends 'base.html' %}{% block title %}{{ 'Editar' if per else 'Nueva' }} persona{% endblock %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-6">
<div class="card"><div class="card-header"><h5 class="mb-0">{{ 'Editar' if per else 'Nueva' }} persona</h5></div>
<div class="card-body">
<form method="post">
  <div class="row g-3">
    <div class="col-12"><label class="form-label">Nombre <span class="text-danger">*</span></label>
      <input type="text" name="nombre" class="form-control" value="{{ per.nombre if per else '' }}" required autofocus></div>
    <div class="col-md-6"><label class="form-label">Primer apellido <span class="text-danger">*</span></label>
      <input type="text" name="apellido1" class="form-control" value="{{ per.apellido1 if per else '' }}" required></div>
    <div class="col-md-6"><label class="form-label">Segundo apellido</label>
      <input type="text" name="apellido2" class="form-control" value="{{ per.apellido2 if per else '' }}"></div>
    <div class="col-md-6"><label class="form-label">DNI <span class="text-danger">*</span></label>
      <input type="text" name="dni" class="form-control font-monospace" value="{{ per.dni if per else '' }}" required></div>
    <div class="col-md-6"><label class="form-label">Oficio</label>
      <input type="text" name="oficio" class="form-control" value="{{ per.oficio if per else '' }}" placeholder="Chapista, electricista..."></div>
    <div class="col-12"><label class="form-label">Empresa</label>
      <select name="id_empresa" class="form-select">
        <option value="">— Sin empresa —</option>
        {% for e in empresas %}<option value="{{ e.id_empresa }}" {{ 'selected' if per and per.id_empresa==e.id_empresa }}>{{ e.nombre }}</option>{% endfor %}
      </select></div>
    {% if per %}
    <div class="col-12"><label class="form-label">Estado</label>
      <select name="estado" class="form-select">
        <option value="activa" {{ 'selected' if per.estado=='activa' }}>Activa</option>
        <option value="inactiva" {{ 'selected' if per.estado=='inactiva' }}>Inactiva</option>
      </select></div>
    {% endif %}
    <div class="col-12 d-flex gap-2">
      <button type="submit" class="btn btn-opl">Guardar</button>
      <a href="{{ url_for('personas') }}" class="btn btn-secondary">Cancelar</a>
    </div>
  </div>
</form></div></div></div></div>{% endblock %}"""

# ── OBRAS ─────────────────────────────────────────────────────────────────────
T['obras.html'] = r"""{% extends 'base.html' %}{% block title %}Obras{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h2 class="h4 mb-0"><i class="bi bi-buildings"></i> Obras</h2>
  <a href="{{ url_for('obra_nueva') }}" class="btn btn-opl btn-sm"><i class="bi bi-plus"></i> Nueva obra</a>
</div>
<div class="card"><div class="card-body p-0">
<table class="table table-hover mb-0">
  <thead><tr><th>Código</th><th>Nombre</th><th>Empresas</th><th>Estado</th><th class="text-end">Acciones</th></tr></thead>
  <tbody>
  {% for o in obras %}
  <tr>
    <td class="font-monospace fw-bold">{{ o.codigo }}</td>
    <td>{{ o.nombre }}</td>
    <td><span class="badge bg-secondary">{{ o.n_e }}</span></td>
    <td><span class="badge badge-{{ o.estado }}">{{ o.estado }}</span></td>
    <td class="text-end">
      <a href="{{ url_for('obra_editar', id_=o.id_obra) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="post" action="{{ url_for('obra_estado', id_=o.id_obra) }}" class="d-inline">
        <button class="btn btn-sm btn-outline-{{ 'warning' if o.estado=='activa' else 'success' }}" title="{{ 'Finalizar' if o.estado=='activa' else 'Reactivar' }}">
          <i class="bi bi-{{ 'pause' if o.estado=='activa' else 'play' }}"></i>
        </button>
      </form>
      <form method="post" action="{{ url_for('obra_eliminar', id_=o.id_obra) }}" class="d-inline" onsubmit="return confirm('¿Eliminar obra {{ o.nombre }}?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button>
      </form>
    </td>
  </tr>
  {% else %}
  <tr><td colspan="5" class="text-center text-muted py-4">Sin obras. <a href="{{ url_for('obra_nueva') }}">Crear una</a>.</td></tr>
  {% endfor %}
  </tbody>
</table>
</div></div>{% endblock %}"""

T['obra_form.html'] = r"""{% extends 'base.html' %}{% block title %}{{ 'Editar' if obra else 'Nueva' }} obra{% endblock %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-6">
<div class="card"><div class="card-header"><h5 class="mb-0">{{ 'Editar' if obra else 'Nueva' }} obra</h5></div>
<div class="card-body">
<form method="post">
  <div class="mb-3"><label class="form-label">Código <span class="text-danger">*</span></label>
    <input type="text" name="codigo" class="form-control font-monospace" value="{{ obra.codigo if obra else '' }}" required autofocus placeholder="Ej: 2516"></div>
  <div class="mb-3"><label class="form-label">Nombre <span class="text-danger">*</span></label>
    <input type="text" name="nombre" class="form-control" value="{{ obra.nombre if obra else '' }}" required></div>
  {% if obra %}
  <div class="mb-3"><label class="form-label">Estado</label>
    <select name="estado" class="form-select">
      <option value="activa" {{ 'selected' if obra.estado=='activa' }}>Activa</option>
      <option value="finalizada" {{ 'selected' if obra.estado=='finalizada' }}>Finalizada</option>
    </select></div>
  <div class="mb-3">
    <div class="sec"><i class="bi bi-briefcase"></i> Empresas participantes</div>
    {% for e in empresas %}
    <div class="form-check">
      <input class="form-check-input" type="checkbox" name="empresas" value="{{ e.id_empresa }}" id="e{{ e.id_empresa }}"
        {{ 'checked' if e.id_empresa in oe_ids }}>
      <label class="form-check-label" for="e{{ e.id_empresa }}">{{ e.nombre }}</label>
    </div>
    {% endfor %}
  </div>
  {% endif %}
  <div class="d-flex gap-2">
    <button type="submit" class="btn btn-opl">Guardar</button>
    <a href="{{ url_for('obras') }}" class="btn btn-secondary">Cancelar</a>
  </div>
</form></div></div></div></div>{% endblock %}"""

# ── DIARIO ────────────────────────────────────────────────────────────────────
T['diario_sel.html'] = r"""{% extends 'base.html' %}{% block title %}Diario{% endblock %}
{% block content %}
<h2 class="h4 mb-3"><i class="bi bi-calendar-day"></i> Seleccionar parte diario</h2>
<div class="row justify-content-center"><div class="col-md-5">
<div class="card"><div class="card-body">
<form method="get" action="{{ url_for('diario_redir') }}">
  <div class="mb-3"><label class="form-label">Obra <span class="text-danger">*</span></label>
    <select name="id_obra" class="form-select" required>
      <option value="">— Selecciona obra —</option>
      {% for o in obras %}<option value="{{ o.id_obra }}">{{ o.codigo }} · {{ o.nombre }}</option>{% endfor %}
    </select></div>
  <div class="mb-3"><label class="form-label">Fecha <span class="text-danger">*</span></label>
    <input type="date" name="fecha" class="form-control" value="{{ hoy }}" required></div>
  <button type="submit" class="btn btn-opl w-100"><i class="bi bi-arrow-right-circle"></i> Abrir parte</button>
</form></div></div></div></div>{% endblock %}"""

T['diario_ver.html'] = r"""{% extends 'base.html' %}{% block title %}Parte {{ fecha }}{% endblock %}
{% block head %}
<style>
.emp-block{border:1px solid #374151;border-radius:8px;padding:1rem;margin-bottom:1rem;background:#111827}
.emp-title{font-weight:700;color:#f97316;margin-bottom:.75rem}
.linea-row{background:#1a1d27;border-radius:6px;padding:.5rem .75rem;margin-bottom:.4rem;display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.linea-del{margin-left:auto}
</style>{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
  <h2 class="h4 mb-0"><i class="bi bi-calendar-day"></i> Parte · {{ obra.codigo }} {{ obra.nombre }} · {{ fecha }}</h2>
  <div class="d-flex gap-2">
    {% if prev_d %}<a href="{{ url_for('diario_ver', id_obra=obra.id_obra, fecha=prev_d) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-chevron-left"></i></a>{% endif %}
    {% if next_d %}<a href="{{ url_for('diario_ver', id_obra=obra.id_obra, fecha=next_d) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-chevron-right"></i></a>{% endif %}
    <a href="{{ url_for('diario_sel') }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-calendar3"></i> Cambiar</a>
  </div>
</div>

{# ── Aviso arrastre ─────────────────────────────────────────────────────────── #}
{% if arr_fecha and arr_lineas %}
<div class="alert alert-info alert-dismissible fade show py-2">
  <strong><i class="bi bi-clipboard-check"></i> Arrastre disponible</strong> — Hay {{ arr_lineas|length }} línea(s) del parte del día <strong>{{ arr_fecha }}</strong>.
  <form method="post" action="{{ url_for('diario_arrastrar', id_obra=obra.id_obra, fecha=fecha) }}" class="d-inline ms-2">
    <button class="btn btn-sm btn-opl"><i class="bi bi-copy"></i> Copiar líneas</button>
  </form>
  <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
</div>
{% endif %}

{# ── Bloque por empresa ─────────────────────────────────────────────────────── #}
{% for emp, lineas in por_empresa.items() %}
<div class="emp-block">
  <div class="emp-title"><i class="bi bi-briefcase"></i> {{ emp }}</div>
  {% for l in lineas %}
  <div class="linea-row">
    <span class="badge bg-secondary">{{ l.persona }}</span>
    <span class="text-muted small">{{ l.asunto or '—' }}</span>
    <span class="badge bg-primary ms-auto">{{ hhmm(l.horas) }}</span>
    <a href="{{ url_for('dl_editar', id_dl=l.id_dl) }}" class="btn btn-xs btn-outline-secondary btn-sm py-0 px-1"><i class="bi bi-pencil"></i></a>
    <form method="post" action="{{ url_for('dl_eliminar', id_dl=l.id_dl) }}" class="d-inline linea-del" onsubmit="return confirm('¿Eliminar esta línea?')">
      <button class="btn btn-xs btn-outline-danger btn-sm py-0 px-1"><i class="bi bi-x"></i></button>
    </form>
  </div>
  {% endfor %}
</div>
{% endfor %}

{# ── Añadir línea ───────────────────────────────────────────────────────────── #}
{% if empresas_obra %}
<div class="sec mt-3"><i class="bi bi-plus-circle"></i> Añadir persona al parte</div>
<div class="card"><div class="card-body">
<form method="post" action="{{ url_for('dl_nueva', id_obra=obra.id_obra, fecha=fecha) }}">
  <div class="row g-2 align-items-end">
    <div class="col-md-3">
      <label class="form-label small">Empresa</label>
      <select name="id_empresa" id="selEmp" class="form-select form-select-sm" onchange="filtrarPersonas()" required>
        <option value="">— Empresa —</option>
        {% for e in empresas_obra %}<option value="{{ e.id_empresa }}">{{ e.nombre }}</option>{% endfor %}
      </select>
    </div>
    <div class="col-md-3">
      <label class="form-label small">Persona</label>
      <select name="id_persona" id="selPer" class="form-select form-select-sm" required>
        <option value="">— Persona —</option>
        {% for p in personas_obra %}<option value="{{ p.id_persona }}" data-emp="{{ p.id_empresa }}">{{ p.apellido1 }} {{ p.nombre }}</option>{% endfor %}
      </select>
    </div>
    <div class="col-md-3">
      <label class="form-label small">Asunto</label>
      <input type="text" name="asunto" class="form-control form-control-sm" placeholder="Descripción tarea">
    </div>
    <div class="col-md-2">
      <label class="form-label small">Horas (HH.MM)</label>
      <input type="number" name="horas" class="form-control form-control-sm" step="0.25" min="0" max="24" value="8" required>
    </div>
    <div class="col-md-1">
      <button type="submit" class="btn btn-opl btn-sm w-100"><i class="bi bi-plus"></i></button>
    </div>
  </div>
</form>
</div></div>
{% else %}
<div class="alert alert-warning"><i class="bi bi-exclamation-triangle"></i> Esta obra no tiene empresas asignadas. <a href="{{ url_for('obra_editar', id_=obra.id_obra) }}">Añadir empresas</a>.</div>
{% endif %}
{% endblock %}
{% block scripts %}
<script>
function filtrarPersonas(){
  const v=document.getElementById('selEmp').value;
  document.querySelectorAll('#selPer option').forEach(o=>{
    if(!o.value)return;
    o.style.display=(v===''||o.dataset.emp===v)?'':'none';
  });
  const sel=document.getElementById('selPer');
  if(sel.options[sel.selectedIndex]?.style.display==='none') sel.value='';
}
</script>{% endblock %}"""

T['dl_form.html'] = r"""{% extends 'base.html' %}{% block title %}Editar línea{% endblock %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-6">
<div class="card"><div class="card-header"><h5 class="mb-0">Editar línea de parte</h5></div>
<div class="card-body">
<p class="text-muted small">Parte: <strong>{{ dl.fecha }}</strong> · {{ dl.obra }}</p>
<form method="post">
  <div class="mb-3"><label class="form-label">Persona</label>
    <input type="text" class="form-control" value="{{ dl.persona }}" disabled></div>
  <div class="mb-3"><label class="form-label">Asunto</label>
    <input type="text" name="asunto" class="form-control" value="{{ dl.asunto }}"></div>
  <div class="mb-3"><label class="form-label">Horas</label>
    <input type="number" name="horas" class="form-control" step="0.25" min="0" max="24" value="{{ dl.horas }}" required></div>
  <div class="d-flex gap-2">
    <button type="submit" class="btn btn-opl">Guardar</button>
    <a href="{{ url_for('diario_ver', id_obra=dl.id_obra, fecha=dl.fecha) }}" class="btn btn-secondary">Cancelar</a>
  </div>
</form></div></div></div></div>{% endblock %}"""

# ── MENSUAL ───────────────────────────────────────────────────────────────────
T['mensual_sel.html'] = r"""{% extends 'base.html' %}{% block title %}Mensual{% endblock %}
{% block content %}
<h2 class="h4 mb-3"><i class="bi bi-calendar-month"></i> Seleccionar parte mensual</h2>
<div class="row justify-content-center"><div class="col-md-5">
<div class="card"><div class="card-body">
<form method="get" action="{{ url_for('mensual_ver') }}">
  <div class="mb-3"><label class="form-label">Obra <span class="text-danger">*</span></label>
    <select name="id_obra" class="form-select" required>
      <option value="">— Selecciona obra —</option>
      {% for o in obras %}<option value="{{ o.id_obra }}">{{ o.codigo }} · {{ o.nombre }}</option>{% endfor %}
    </select></div>
  <div class="mb-3"><label class="form-label">Empresa <span class="text-danger">*</span></label>
    <select name="id_empresa" class="form-select" required>
      <option value="">— Selecciona empresa —</option>
      {% for e in empresas %}<option value="{{ e.id_empresa }}">{{ e.nombre }}</option>{% endfor %}
    </select></div>
  <div class="mb-3"><label class="form-label">Mes <span class="text-danger">*</span></label>
    <input type="month" name="mes" class="form-control" value="{{ mes_actual }}" required></div>
  <button type="submit" class="btn btn-opl w-100"><i class="bi bi-table"></i> Ver mensual</button>
</form></div></div></div></div>{% endblock %}"""

T['mensual_ver.html'] = r"""{% extends 'base.html' %}{% block title %}Mensual {{ mes }}{% endblock %}
{% block head %}
<style>
.tabla-mens{font-size:.75rem;overflow-x:auto;display:block}
.tabla-mens th,.tabla-mens td{white-space:nowrap;padding:3px 5px}
.htd-val{font-family:monospace;text-align:center;min-width:38px}
.fila-total{font-weight:700;color:#f97316}
</style>{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
  <div>
    <h2 class="h4 mb-0"><i class="bi bi-calendar-month"></i> {{ empresa.nombre }}</h2>
    <div class="text-muted small">Obra: <strong>{{ obra.codigo }} · {{ obra.nombre }}</strong> · Mes: <strong>{{ mes }}</strong></div>
  </div>
  <div class="d-flex gap-2 flex-wrap">
    <span class="badge badge-{{ estado }} fs-6">{{ estado }}</span>
    {% if estado=='abierto' %}
    <form method="post" action="{{ url_for('mensual_cerrar', id_obra=obra.id_obra, id_empresa=empresa.id_empresa, mes=mes) }}" onsubmit="return confirm('¿Cerrar el mes {{ mes }}? Esta acción es DEFINITIVA.')">
      <button class="btn btn-sm btn-warning"><i class="bi bi-lock"></i> Cerrar mes</button>
    </form>
    {% endif %}
    <a href="{{ url_for('mensual_csv', id_obra=obra.id_obra, id_empresa=empresa.id_empresa, mes=mes) }}" class="btn btn-sm btn-success"><i class="bi bi-file-earmark-spreadsheet"></i> Exportar Excel</a>
    <a href="{{ url_for('mensual_sel') }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-arrow-left"></i></a>
  </div>
</div>
{% if estado=='cerrado' %}
<div class="alert alert-secondary py-2"><i class="bi bi-lock-fill"></i> Mes cerrado. Los datos son un snapshot congelado.</div>
{% endif %}
<div class="tabla-mens">
<table class="table table-bordered table-sm mb-0">
  <thead class="table-dark">
    <tr>
      <th style="min-width:160px">Nombre y apellidos</th>
      <th style="min-width:90px">DNI</th>
      {% for d in dias %}<th class="hth">{{ d }}</th>{% endfor %}
      <th class="hth fila-total">TOTAL</th>
    </tr>
  </thead>
  <tbody>
  {% for row in filas %}
  <tr>
    <td>{{ row.ap1 }} {{ row.ap2 }}, {{ row.nom }}</td>
    <td class="font-monospace small">{{ row.dni }}</td>
    {% for h in row.horas_dias %}<td class="htd-val">{{ hhmm(h) }}</td>{% endfor %}
    <td class="htd-val fila-total">{{ hhmm(row.total) }}</td>
  </tr>
  {% else %}
  <tr><td colspan="{{ dias|length + 3 }}" class="text-center text-muted py-3">No hay datos de presencia para este mes.</td></tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% endblock %}"""

# ── BACKUP ────────────────────────────────────────────────────────────────────
T['backup.html'] = r"""{% extends 'base.html' %}{% block title %}Backup{% endblock %}
{% block content %}
<h2 class="h4 mb-3"><i class="bi bi-database"></i> Gestión de Backup</h2>
<div class="row g-4">
  <div class="col-md-5">
    <div class="card"><div class="card-header sec mb-0"><i class="bi bi-cloud-download"></i> Crear backup</div>
    <div class="card-body">
      <p class="text-muted small">Se recomienda crear backup antes de cerrar un mes o realizar cambios importantes. El fichero incluye el contexto de la obra seleccionada en el nombre.</p>
      <form method="post" action="{{ url_for('backup_crear') }}">
        <div class="mb-3"><label class="form-label">Contexto (obra)</label>
          <select name="id_obra" class="form-select">
            <option value="">— General (sin obra) —</option>
            {% for o in obras %}<option value="{{ o.id_obra }}">{{ o.codigo }} · {{ o.nombre }}</option>{% endfor %}
          </select></div>
        <button type="submit" class="btn btn-opl w-100"><i class="bi bi-download"></i> Crear backup ahora</button>
      </form>
    </div></div>
  </div>
  <div class="col-md-7">
    <div class="card"><div class="card-header sec mb-0"><i class="bi bi-archive"></i> Backups disponibles</div>
    <div class="card-body p-0">
    <table class="table table-hover mb-0">
      <thead><tr><th>Fichero</th><th class="text-end">Acciones</th></tr></thead>
      <tbody>
      {% for b in backups %}
      <tr>
        <td class="small font-monospace">{{ b }}</td>
        <td class="text-end">
          <form method="post" action="{{ url_for('backup_restaurar') }}" class="d-inline"
            onsubmit="return confirm('⚠️ ATENCIÓN: Restaurar reemplazará TODOS los datos actuales con los del backup seleccionado. Es un borrón y cuenta nueva. ¿Continuar?')">
            <input type="hidden" name="fichero" value="{{ b }}">
            <button class="btn btn-sm btn-outline-danger"><i class="bi bi-arrow-counterclockwise"></i> Restaurar</button>
          </form>
        </td>
      </tr>
      {% else %}
      <tr><td colspan="2" class="text-center text-muted py-3">Sin backups. Crea uno usando el formulario.</td></tr>
      {% endfor %}
      </tbody>
    </table>
    </div></div>
  </div>
</div>{% endblock %}"""

# ── CONFIG ────────────────────────────────────────────────────────────────────
T['config.html'] = r"""{% extends 'base.html' %}{% block title %}Configuración{% endblock %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-5">
<h2 class="h4 mb-3"><i class="bi bi-gear"></i> Configuración</h2>
<div class="card"><div class="card-body">
<form method="post">
  <div class="mb-3">
    <label class="form-label">Límite de horas por persona y día <span class="text-danger">*</span></label>
    <input type="number" name="limite" class="form-control" step="0.5" min="0.5" max="24" value="{{ lim }}" required>
    <div class="form-text">Máximo total de horas (sumando todas las obras) que puede registrar una persona en un día. Por defecto: 24h.</div>
  </div>
  <div class="d-flex gap-2">
    <button type="submit" class="btn btn-opl">Guardar</button>
    <button type="submit" name="reset" value="1" class="btn btn-outline-secondary" onclick="return confirm('¿Restablecer límite a 24h?')">Restablecer a 24h</button>
  </div>
</form></div></div></div></div>{% endblock %}"""

# ── FAQ ───────────────────────────────────────────────────────────────────────
T['faq.html'] = r"""{% extends 'base.html' %}{% block title %}FAQ{% endblock %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-8">
<h2 class="h4 mb-3"><i class="bi bi-question-circle"></i> Preguntas frecuentes</h2>
<div class="accordion" id="faqAcc">

  <div class="accordion-item">
    <h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#f1">
      ¿Qué es el límite de horas/día?
    </button></h2>
    <div id="f1" class="accordion-collapse collapse" data-bs-parent="#faqAcc">
      <div class="accordion-body text-muted small">
        El sistema impide que una persona supere el número de horas configurado en un mismo día, sumando <strong>todas</strong> las obras y empresas en las que trabaje ese día. Por defecto es 24 h/día. Puedes cambiarlo en <a href="/config">Configuración</a>. Si intentas superar el límite, el parte <strong>no se guarda</strong> y el sistema te indica cuántas horas tiene ya registradas.
      </div>
    </div>
  </div>

  <div class="accordion-item">
    <h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#f2">
      ¿Qué significa "Cerrar mes"?
    </button></h2>
    <div id="f2" class="accordion-collapse collapse" data-bs-parent="#faqAcc">
      <div class="accordion-body text-muted small">
        Al cerrar un mes para una obra+empresa, el sistema <strong>congela un snapshot</strong> de los datos (nombre, DNI, horas por día) en ese momento. Después del cierre <strong>no se pueden modificar</strong> partes de ese mes para esa combinación. Esta acción es <strong>definitiva</strong>: si cometiste un error, usa un backup previo.
      </div>
    </div>
  </div>

  <div class="accordion-item">
    <h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#f3">
      ¿Qué hace el backup y la restauración?
    </button></h2>
    <div id="f3" class="accordion-collapse collapse" data-bs-parent="#faqAcc">
      <div class="accordion-body text-muted small">
        <strong>Backup:</strong> copia toda la base de datos a un fichero <code>.db</code> en la carpeta <code>backups/</code>. Se puede hacer en caliente, sin cerrar la app.<br>
        <strong>Restauración:</strong> reemplaza completamente la base de datos actual por el contenido del backup seleccionado. Es un <strong>borrón y cuenta nueva</strong>. Úsalo solo en casos de desastre, no para "probar cosas".
      </div>
    </div>
  </div>

  <div class="accordion-item">
    <h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#f4">
      ¿Por qué las horas se ven como 08:00 en vez de 8.0?
    </button></h2>
    <div id="f4" class="accordion-collapse collapse" data-bs-parent="#faqAcc">
      <div class="accordion-body text-muted small">
        Internamente las horas se guardan en formato decimal para poder sumar y validar sin problemas. En la pantalla y en los exports CSV se convierten a formato <code>HH:MM</code> para facilitar la lectura y el uso en Excel. Puedes ingresar horas con decimales (p. ej. <code>8.5</code> = 8 horas y 30 minutos).
      </div>
    </div>
  </div>

  <div class="accordion-item">
    <h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#f5">
      ¿Qué pasa si cambio el límite diario de horas?
    </button></h2>
    <div id="f5" class="accordion-collapse collapse" data-bs-parent="#faqAcc">
      <div class="accordion-body text-muted small">
        El cambio afecta solo a futuras validaciones, no de forma retroactiva. Los registros ya existentes no se borran ni se modifican. El jefe de obra es responsable de que el valor sea correcto.
      </div>
    </div>
  </div>

  <div class="accordion-item">
    <h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#f6">
      ¿Por qué no puedo modificar un mes cerrado?
    </button></h2>
    <div id="f6" class="accordion-collapse collapse" data-bs-parent="#faqAcc">
      <div class="accordion-body text-muted small">
        El cierre protege el histórico de partes ya emitidos o enviados. Si necesitas corregir algo tras el cierre, usa un backup anterior a la firma/envío del mensual. Los errores se documentan y corrigen en el mes siguiente si es posible.
      </div>
    </div>
  </div>

  <div class="accordion-item">
    <h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#f7">
      ¿Qué es el "arrastre" de líneas del día anterior?
    </button></h2>
    <div id="f7" class="accordion-collapse collapse" data-bs-parent="#faqAcc">
      <div class="accordion-body text-muted small">
        Cuando abres un parte de una fecha que aún no tiene entradas, el sistema detecta si existe un parte anterior para la misma obra y te ofrece copiar las líneas (personas y asuntos) de ese parte anterior, con horas a 0 para que las rellenes. Las horas nunca se copian automáticamente. Puedes aceptar o ignorar el aviso.
      </div>
    </div>
  </div>

</div>
</div></div>{% endblock %}"""

# ── SETUP LOADER ─────────────────────────────────────────────────────────────
app.jinja_loader = ChoiceLoader([DL(T), app.jinja_loader])
app.jinja_env.globals['hhmm'] = hhmm

# ═══════════════════════════════════════════════════════════════════════════════
#  RUTAS ── INDEX
# ═══════════════════════════════════════════════════════════════════════════════
@app.route('/')
def index():
    with app.app_context():
        init_db()
    db = get_db()
    hoy = date.today()
    obras = db.execute("SELECT * FROM obra WHERE estado='activa'").fetchall()
    return render_template('index.html', act='home',
        hoy=hoy.strftime('%d/%m/%Y'), hoy_iso=hoy.isoformat(),
        n_obras=db.execute("SELECT COUNT(*) FROM obra WHERE estado='activa'").fetchone()[0],
        n_emp=db.execute("SELECT COUNT(*) FROM empresa WHERE estado='activa'").fetchone()[0],
        n_per=db.execute("SELECT COUNT(*) FROM persona WHERE estado='activa'").fetchone()[0],
        lim=get_lim(), obras=obras)

# ═══════════════════════════════════════════════════════════════════════════════
#  RUTAS ── EMPRESAS
# ═══════════════════════════════════════════════════════════════════════════════
@app.route('/empresas')
def empresas():
    db = get_db()
    rows = db.execute("""
        SELECT e.*,
            (SELECT COUNT(*) FROM persona p WHERE p.id_empresa=e.id_empresa) n_p,
            (SELECT COUNT(*) FROM obra_empresa oe WHERE oe.id_empresa=e.id_empresa) n_o
        FROM empresa e ORDER BY e.nombre""").fetchall()
    return render_template('empresas.html', act='empresas', empresas=rows)

@app.route('/empresas/nueva', methods=['GET','POST'])
def empresa_nueva():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        try:
            get_db().execute('INSERT INTO empresa(nombre) VALUES(?)', [nombre])
            get_db().commit(); flash(f'Empresa "{nombre}" creada.', 'success')
            return redirect(url_for('empresas'))
        except sqlite3.IntegrityError:
            flash(f'Ya existe una empresa con ese nombre.', 'error')
    return render_template('empresa_form.html', act='empresas', emp=None)

@app.route('/empresas/<int:id_>/editar', methods=['GET','POST'])
def empresa_editar(id_):
    db = get_db()
    emp = db.execute('SELECT * FROM empresa WHERE id_empresa=?', [id_]).fetchone()
    if not emp: flash('Empresa no encontrada.', 'error'); return redirect(url_for('empresas'))
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        estado = request.form['estado']
        try:
            db.execute('UPDATE empresa SET nombre=?,estado=? WHERE id_empresa=?', [nombre, estado, id_])
            db.commit(); flash('Empresa actualizada.', 'success')
            return redirect(url_for('empresas'))
        except sqlite3.IntegrityError:
            flash('Ya existe una empresa con ese nombre.', 'error')
    return render_template('empresa_form.html', act='empresas', emp=emp)

@app.route('/empresas/<int:id_>/estado', methods=['POST'])
def empresa_estado(id_):
    db = get_db()
    e = db.execute('SELECT estado FROM empresa WHERE id_empresa=?', [id_]).fetchone()
    if e:
        nuevo = 'finalizada' if e['estado'] == 'activa' else 'activa'
        db.execute('UPDATE empresa SET estado=? WHERE id_empresa=?', [nuevo, id_])
        db.commit()
    return redirect(url_for('empresas'))

@app.route('/empresas/<int:id_>/eliminar', methods=['POST'])
def empresa_eliminar(id_):
    try:
        get_db().execute('DELETE FROM empresa WHERE id_empresa=?', [id_])
        get_db().commit(); flash('Empresa eliminada.', 'success')
    except sqlite3.IntegrityError:
        flash(M['fk'], 'error')
    return redirect(url_for('empresas'))

# ═══════════════════════════════════════════════════════════════════════════════
#  RUTAS ── PERSONAS
# ═══════════════════════════════════════════════════════════════════════════════
@app.route('/personas')
def personas():
    db = get_db()
    q = request.args.get('q','').strip()
    id_emp = request.args.get('id_empresa','')
    sql = """SELECT p.*, e.nombre empresa FROM persona p
             LEFT JOIN empresa e ON p.id_empresa=e.id_empresa WHERE 1=1"""
    params = []
    if q:
        sql += " AND (p.nombre||' '||p.apellido1||' '||p.apellido2||' '||p.dni||' '||p.oficio LIKE ?)"
        params.append(f'%{q}%')
    if id_emp:
        sql += " AND p.id_empresa=?"
        params.append(id_emp)
    sql += " ORDER BY p.apellido1,p.apellido2,p.nombre"
    rows = db.execute(sql, params).fetchall()
    emps = db.execute("SELECT * FROM empresa ORDER BY nombre").fetchall()
    return render_template('personas.html', act='personas', personas=rows, empresas=emps, q=q, id_emp=id_emp)

@app.route('/personas/nueva', methods=['GET','POST'])
def persona_nueva():
    db = get_db()
    if request.method == 'POST':
        try:
            db.execute("""INSERT INTO persona(nombre,apellido1,apellido2,dni,id_empresa,oficio)
                          VALUES(?,?,?,?,?,?)""",
                [request.form['nombre'].strip(), request.form['apellido1'].strip(),
                 request.form['apellido2'].strip(), request.form['dni'].strip().upper(),
                 request.form['id_empresa'] or None, request.form['oficio'].strip()])
            db.commit(); flash('Persona creada.', 'success')
            return redirect(url_for('personas'))
        except sqlite3.IntegrityError:
            flash('El DNI ya existe en la base de datos.', 'error')
    emps = db.execute("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").fetchall()
    return render_template('persona_form.html', act='personas', per=None, empresas=emps)

@app.route('/personas/<int:id_>/editar', methods=['GET','POST'])
def persona_editar(id_):
    db = get_db()
    per = db.execute('SELECT * FROM persona WHERE id_persona=?', [id_]).fetchone()
    if not per: flash('Persona no encontrada.', 'error'); return redirect(url_for('personas'))
    if request.method == 'POST':
        try:
            db.execute("""UPDATE persona SET nombre=?,apellido1=?,apellido2=?,dni=?,
                          id_empresa=?,oficio=?,estado=? WHERE id_persona=?""",
                [request.form['nombre'].strip(), request.form['apellido1'].strip(),
                 request.form['apellido2'].strip(), request.form['dni'].strip().upper(),
                 request.form['id_empresa'] or None, request.form['oficio'].strip(),
                 request.form.get('estado', per['estado']), id_])
            db.commit(); flash('Persona actualizada.', 'success')
            return redirect(url_for('personas'))
        except sqlite3.IntegrityError:
            flash('El DNI ya existe en otro registro.', 'error')
    emps = db.execute("SELECT * FROM empresa ORDER BY nombre").fetchall()
    return render_template('persona_form.html', act='personas', per=per, empresas=emps)

@app.route('/personas/<int:id_>/estado', methods=['POST'])
def persona_estado(id_):
    db = get_db()
    p = db.execute('SELECT estado FROM persona WHERE id_persona=?', [id_]).fetchone()
    if p:
        nuevo = 'inactiva' if p['estado'] == 'activa' else 'activa'
        db.execute('UPDATE persona SET estado=? WHERE id_persona=?', [nuevo, id_])
        db.commit()
    return redirect(url_for('personas'))

@app.route('/personas/<int:id_>/eliminar', methods=['POST'])
def persona_eliminar(id_):
    try:
        get_db().execute('DELETE FROM persona WHERE id_persona=?', [id_])
        get_db().commit(); flash('Persona eliminada.', 'success')
    except sqlite3.IntegrityError:
        flash(M['fk'] + ' Márcala como inactiva en su lugar.', 'error')
    return redirect(url_for('personas'))

# ═══════════════════════════════════════════════════════════════════════════════
#  RUTAS ── OBRAS
# ═══════════════════════════════════════════════════════════════════════════════
@app.route('/obras')
def obras():
    db = get_db()
    rows = db.execute("""SELECT o.*,
        (SELECT COUNT(*) FROM obra_empresa oe WHERE oe.id_obra=o.id_obra) n_e
        FROM obra o ORDER BY o.codigo""").fetchall()
    return render_template('obras.html', act='obras', obras=rows)

@app.route('/obras/nueva', methods=['GET','POST'])
def obra_nueva():
    if request.method == 'POST':
        codigo = request.form['codigo'].strip()
        nombre = request.form['nombre'].strip()
        try:
            get_db().execute('INSERT INTO obra(codigo,nombre) VALUES(?,?)', [codigo, nombre])
            get_db().commit(); flash(f'Obra "{nombre}" creada.', 'success')
            return redirect(url_for('obras'))
        except sqlite3.IntegrityError:
            flash('Ya existe una obra con ese código.', 'error')
    return render_template('obra_form.html', act='obras', obra=None, empresas=[], oe_ids=[])

@app.route('/obras/<int:id_>/editar', methods=['GET','POST'])
def obra_editar(id_):
    db = get_db()
    obra = db.execute('SELECT * FROM obra WHERE id_obra=?', [id_]).fetchone()
    if not obra: flash('Obra no encontrada.', 'error'); return redirect(url_for('obras'))
    if request.method == 'POST':
        codigo = request.form['codigo'].strip()
        nombre = request.form['nombre'].strip()
        estado = request.form['estado']
        sel_emps = set(int(x) for x in request.form.getlist('empresas'))
        try:
            db.execute('UPDATE obra SET codigo=?,nombre=?,estado=? WHERE id_obra=?', [codigo, nombre, estado, id_])
            # Sync obra_empresa
            act_emps = set(r['id_empresa'] for r in db.execute('SELECT id_empresa FROM obra_empresa WHERE id_obra=?', [id_]).fetchall())
            for eid in sel_emps - act_emps:
                db.execute('INSERT OR IGNORE INTO obra_empresa(id_obra,id_empresa) VALUES(?,?)', [id_, eid])
            for eid in act_emps - sel_emps:
                try: db.execute('DELETE FROM obra_empresa WHERE id_obra=? AND id_empresa=?', [id_, eid])
                except sqlite3.IntegrityError: pass
            db.commit(); flash('Obra actualizada.', 'success')
            return redirect(url_for('obras'))
        except sqlite3.IntegrityError:
            flash('Ya existe una obra con ese código.', 'error')
    emps = db.execute("SELECT * FROM empresa ORDER BY nombre").fetchall()
    oe_ids = [r['id_empresa'] for r in db.execute('SELECT id_empresa FROM obra_empresa WHERE id_obra=?', [id_]).fetchall()]
    return render_template('obra_form.html', act='obras', obra=obra, empresas=emps, oe_ids=oe_ids)

@app.route('/obras/<int:id_>/estado', methods=['POST'])
def obra_estado(id_):
    db = get_db()
    o = db.execute('SELECT estado FROM obra WHERE id_obra=?', [id_]).fetchone()
    if o:
        nuevo = 'finalizada' if o['estado'] == 'activa' else 'activa'
        db.execute('UPDATE obra SET estado=? WHERE id_obra=?', [nuevo, id_])
        db.commit()
    return redirect(url_for('obras'))

@app.route('/obras/<int:id_>/eliminar', methods=['POST'])
def obra_eliminar(id_):
    try:
        get_db().execute('DELETE FROM obra WHERE id_obra=?', [id_])
        get_db().commit(); flash('Obra eliminada.', 'success')
    except sqlite3.IntegrityError:
        flash(M['fk'], 'error')
    return redirect(url_for('obras'))

# ═══════════════════════════════════════════════════════════════════════════════
#  RUTAS ── DIARIO
# ═══════════════════════════════════════════════════════════════════════════════
@app.route('/diario')
def diario_sel():
    obras = get_db().execute("SELECT * FROM obra WHERE estado='activa' ORDER BY codigo").fetchall()
    return render_template('diario_sel.html', act='diario', obras=obras, hoy=date.today().isoformat())

@app.route('/diario/ir')
def diario_redir():
    id_obra = request.args.get('id_obra')
    fecha   = request.args.get('fecha')
    if not id_obra or not fecha:
        flash('Selecciona obra y fecha.', 'warning')
        return redirect(url_for('diario_sel'))
    return redirect(url_for('diario_ver', id_obra=id_obra, fecha=fecha))

@app.route('/diario/<int:id_obra>/<fecha>')
def diario_ver(id_obra, fecha):
    db = get_db()
    obra = db.execute('SELECT * FROM obra WHERE id_obra=?', [id_obra]).fetchone()
    if not obra: flash('Obra no encontrada.', 'error'); return redirect(url_for('diario_sel'))

    # Asegurar que existe el registro diario
    db.execute('INSERT OR IGNORE INTO diario(id_obra,fecha) VALUES(?,?)', [id_obra, fecha])
    db.commit()
    diario = db.execute('SELECT * FROM diario WHERE id_obra=? AND fecha=?', [id_obra, fecha]).fetchone()

    # Líneas del parte
    lineas = db.execute("""
        SELECT dl.id_dl, dl.asunto, dl.horas, dl.id_empresa,
               e.nombre emp_n, p.nombre||' '||p.apellido1 persona, p.id_empresa id_p_emp
        FROM diario_linea dl
        JOIN empresa e ON dl.id_empresa=e.id_empresa
        JOIN persona p ON dl.id_persona=p.id_persona
        WHERE dl.id_diario=?
        ORDER BY e.nombre, p.apellido1""", [diario['id_diario']]).fetchall()

    # Agrupar por empresa
    por_empresa = {}
    for l in lineas:
        por_empresa.setdefault(l['emp_n'], []).append(l)

    # Empresas y personas de la obra
    empresas_obra = db.execute("""SELECT e.* FROM empresa e
        JOIN obra_empresa oe ON e.id_empresa=oe.id_empresa
        WHERE oe.id_obra=? AND e.estado='activa' ORDER BY e.nombre""", [id_obra]).fetchall()

    personas_obra = db.execute("""SELECT p.id_persona, p.nombre, p.apellido1, p.id_empresa
        FROM persona p
        JOIN obra_empresa oe ON p.id_empresa=oe.id_empresa
        WHERE oe.id_obra=? AND p.estado='activa'
        ORDER BY p.apellido1, p.nombre""", [id_obra]).fetchall()

    # Arrastre: último parte anterior con líneas
    arr = db.execute("""SELECT d.fecha, d.id_diario FROM diario d
        WHERE d.id_obra=? AND d.fecha<? AND EXISTS
            (SELECT 1 FROM diario_linea dl WHERE dl.id_diario=d.id_diario)
        ORDER BY d.fecha DESC LIMIT 1""", [id_obra, fecha]).fetchone()
    arr_lineas = []
    arr_fecha = None
    if arr and not lineas:  # Solo sugerir si el parte actual está vacío
        arr_fecha = arr['fecha']
        arr_lineas = db.execute('SELECT * FROM diario_linea WHERE id_diario=?', [arr['id_diario']]).fetchall()

    # Nav prev/next
    prev = db.execute("SELECT fecha FROM diario WHERE id_obra=? AND fecha<? ORDER BY fecha DESC LIMIT 1", [id_obra, fecha]).fetchone()
    nxt  = db.execute("SELECT fecha FROM diario WHERE id_obra=? AND fecha>? ORDER BY fecha ASC  LIMIT 1", [id_obra, fecha]).fetchone()

    return render_template('diario_ver.html', act='diario', obra=obra, fecha=fecha,
        por_empresa=por_empresa, empresas_obra=empresas_obra, personas_obra=personas_obra,
        arr_fecha=arr_fecha, arr_lineas=arr_lineas,
        prev_d=prev['fecha'] if prev else None, next_d=nxt['fecha'] if nxt else None)

@app.route('/diario/<int:id_obra>/<fecha>/arrastrar', methods=['POST'])
def diario_arrastrar(id_obra, fecha):
    db = get_db()
    db.execute('INSERT OR IGNORE INTO diario(id_obra,fecha) VALUES(?,?)', [id_obra, fecha])
    db.commit()
    diario_hoy = db.execute('SELECT * FROM diario WHERE id_obra=? AND fecha=?', [id_obra, fecha]).fetchone()

    # Último diario anterior con líneas
    arr = db.execute("""SELECT d.id_diario FROM diario d WHERE d.id_obra=? AND d.fecha<?
        AND EXISTS (SELECT 1 FROM diario_linea dl WHERE dl.id_diario=d.id_diario)
        ORDER BY d.fecha DESC LIMIT 1""", [id_obra, fecha]).fetchone()

    if arr:
        lineas = db.execute('SELECT * FROM diario_linea WHERE id_diario=?', [arr['id_diario']]).fetchall()
        # Verificar mes cerrado por línea
        errors = []
        for l in lineas:
            try:
                chk_mes(id_obra, l['id_empresa'], fecha)
            except ValueError as e:
                errors.append(str(e))
        if errors:
            for e in errors: flash(e, 'error')
            return redirect(url_for('diario_ver', id_obra=id_obra, fecha=fecha))
        for l in lineas:
            db.execute("""INSERT INTO diario_linea(id_diario,id_empresa,id_persona,asunto,horas)
                          VALUES(?,?,?,?,0)""",
                [diario_hoy['id_diario'], l['id_empresa'], l['id_persona'], l['asunto']])
        db.commit()
        flash(f'Se arrastraron {len(lineas)} línea(s) del parte anterior.', 'success')
    else:
        flash('No se encontró un parte anterior con líneas.', 'warning')
    return redirect(url_for('diario_ver', id_obra=id_obra, fecha=fecha))

@app.route('/diario/linea/nueva/<int:id_obra>/<fecha>', methods=['POST'])
def dl_nueva(id_obra, fecha):
    db = get_db()
    id_emp = int(request.form['id_empresa'])
    id_per = int(request.form['id_persona'])
    asunto = request.form.get('asunto','').strip()
    horas  = float(request.form.get('horas', 0))
    try:
        chk_mes(id_obra, id_emp, fecha)
        chk_horas(id_per, fecha, horas)
        db.execute('INSERT OR IGNORE INTO diario(id_obra,fecha) VALUES(?,?)', [id_obra, fecha])
        db.commit()
        diario = db.execute('SELECT * FROM diario WHERE id_obra=? AND fecha=?', [id_obra, fecha]).fetchone()
        db.execute('INSERT INTO diario_linea(id_diario,id_empresa,id_persona,asunto,horas) VALUES(?,?,?,?,?)',
            [diario['id_diario'], id_emp, id_per, asunto, horas])
        db.commit()
    except ValueError as e:
        flash(str(e), 'error')
    return redirect(url_for('diario_ver', id_obra=id_obra, fecha=fecha))

@app.route('/diario/linea/<int:id_dl>/editar', methods=['GET','POST'])
def dl_editar(id_dl):
    db = get_db()
    dl = db.execute("""SELECT dl.*, d.fecha, d.id_obra, o.nombre obra,
                        p.nombre||' '||p.apellido1 persona, e.nombre empresa
                        FROM diario_linea dl
                        JOIN diario d ON dl.id_diario=d.id_diario
                        JOIN obra o ON d.id_obra=o.id_obra
                        JOIN persona p ON dl.id_persona=p.id_persona
                        JOIN empresa e ON dl.id_empresa=e.id_empresa
                        WHERE dl.id_dl=?""", [id_dl]).fetchone()
    if not dl: flash('Línea no encontrada.', 'error'); return redirect(url_for('index'))
    if request.method == 'POST':
        asunto = request.form.get('asunto','').strip()
        horas  = float(request.form.get('horas', dl['horas']))
        try:
            chk_mes(dl['id_obra'], dl['id_empresa'], dl['fecha'])
            chk_horas(dl['id_persona'], dl['fecha'], horas, excl=id_dl)
            db.execute('UPDATE diario_linea SET asunto=?,horas=? WHERE id_dl=?', [asunto, horas, id_dl])
            db.commit(); flash('Línea actualizada.', 'success')
        except ValueError as e:
            flash(str(e), 'error')
        return redirect(url_for('diario_ver', id_obra=dl['id_obra'], fecha=dl['fecha']))
    return render_template('dl_form.html', act='diario', dl=dl)

@app.route('/diario/linea/<int:id_dl>/eliminar', methods=['POST'])
def dl_eliminar(id_dl):
    db = get_db()
    dl = db.execute("""SELECT dl.*, d.fecha, d.id_obra FROM diario_linea dl
                        JOIN diario d ON dl.id_diario=d.id_diario
                        WHERE dl.id_dl=?""", [id_dl]).fetchone()
    if dl:
        try:
            chk_mes(dl['id_obra'], dl['id_empresa'], dl['fecha'])
            db.execute('DELETE FROM diario_linea WHERE id_dl=?', [id_dl])
            db.commit()
        except ValueError as e:
            flash(str(e), 'error')
    return redirect(url_for('diario_ver', id_obra=dl['id_obra'], fecha=dl['fecha']) if dl else url_for('index'))

# ═══════════════════════════════════════════════════════════════════════════════
#  RUTAS ── MENSUAL
# ═══════════════════════════════════════════════════════════════════════════════
@app.route('/mensual')
def mensual_sel():
    db = get_db()
    obras = db.execute("SELECT * FROM obra ORDER BY codigo").fetchall()
    emps  = db.execute("SELECT * FROM empresa ORDER BY nombre").fetchall()
    mes_actual = date.today().strftime('%Y-%m')
    return render_template('mensual_sel.html', act='mensual', obras=obras, empresas=emps, mes_actual=mes_actual)

def _get_mensual_data(id_obra, id_empresa, mes):
    """Calcula las filas del mensual desde diario_linea (modo vivo) o desde snapshot."""
    db = get_db()
    obra    = db.execute('SELECT * FROM obra WHERE id_obra=?', [id_obra]).fetchone()
    empresa = db.execute('SELECT * FROM empresa WHERE id_empresa=?', [id_empresa]).fetchone()

    mensual = db.execute('SELECT * FROM mensual WHERE id_obra=? AND id_empresa=? AND mes=?',
        [id_obra, id_empresa, mes]).fetchone()
    estado = mensual['estado'] if mensual else 'abierto'

    year, month = int(mes[:4]), int(mes[5:])
    n_dias = calendar.monthrange(year, month)[1]
    dias = list(range(1, n_dias+1))

    filas = []
    if estado == 'cerrado' and mensual:
        # Leer snapshot
        rows = db.execute("""SELECT mp.*, p.nombre n, p.apellido1 a1, p.apellido2 a2, p.dni d
            FROM mensual_persona mp JOIN persona p ON mp.id_persona=p.id_persona
            WHERE mp.id_mensual=? ORDER BY mp.ap1_c, mp.nom_c""", [mensual['id_mensual']]).fetchall()
        for r in rows:
            hd = [r[f'd{i}'] for i in range(1, n_dias+1)]
            filas.append({'nom': r['nom_c'], 'ap1': r['ap1_c'], 'ap2': r['ap2_c'],
                          'dni': r['dni_c'], 'horas_dias': hd, 'total': r['total_mes']})
    else:
        # Calcular en vivo desde diarios
        personas_mes = db.execute("""
            SELECT DISTINCT dl.id_persona FROM diario_linea dl
            JOIN diario d ON dl.id_diario=d.id_diario
            WHERE d.id_obra=? AND dl.id_empresa=? AND strftime('%Y-%m',d.fecha)=?
        """, [id_obra, id_empresa, mes]).fetchall()

        for pr in personas_mes:
            pid = pr['id_persona']
            p   = db.execute('SELECT * FROM persona WHERE id_persona=?', [pid]).fetchone()
            hd  = []
            tot = 0.0
            for di in dias:
                fecha_di = f'{year}-{month:02d}-{di:02d}'
                row = db.execute("""
                    SELECT COALESCE(SUM(dl.horas),NULL) h FROM diario_linea dl
                    JOIN diario d ON dl.id_diario=d.id_diario
                    WHERE d.id_obra=? AND dl.id_empresa=? AND dl.id_persona=? AND d.fecha=?
                """, [id_obra, id_empresa, pid, fecha_di]).fetchone()
                h = row['h']
                hd.append(h)
                if h: tot += h
            filas.append({'nom': p['nombre'], 'ap1': p['apellido1'], 'ap2': p['apellido2'],
                          'dni': p['dni'], 'horas_dias': hd, 'total': tot})
        filas.sort(key=lambda x: (x['ap1'], x['nom']))

    return obra, empresa, estado, dias, filas

@app.route('/mensual/ver')
def mensual_ver():
    id_obra    = request.args.get('id_obra', type=int)
    id_empresa = request.args.get('id_empresa', type=int)
    mes        = request.args.get('mes','')
    if not id_obra or not id_empresa or not mes:
        flash('Selecciona obra, empresa y mes.', 'warning')
        return redirect(url_for('mensual_sel'))
    obra, empresa, estado, dias, filas = _get_mensual_data(id_obra, id_empresa, mes)
    return render_template('mensual_ver.html', act='mensual', obra=obra, empresa=empresa,
        mes=mes, estado=estado, dias=dias, filas=filas)

@app.route('/mensual/cerrar/<int:id_obra>/<int:id_empresa>/<mes>', methods=['POST'])
def mensual_cerrar(id_obra, id_empresa, mes):
    db = get_db()
    obra, empresa, estado, dias, filas = _get_mensual_data(id_obra, id_empresa, mes)
    if estado == 'cerrado':
        flash('El mes ya está cerrado.', 'warning')
        return redirect(url_for('mensual_ver', id_obra=id_obra, id_empresa=id_empresa, mes=mes))

    # Crear registro mensual si no existe
    db.execute('INSERT OR IGNORE INTO mensual(id_obra,id_empresa,mes) VALUES(?,?,?)',
        [id_obra, id_empresa, mes])
    db.commit()
    m = db.execute('SELECT * FROM mensual WHERE id_obra=? AND id_empresa=? AND mes=?',
        [id_obra, id_empresa, mes]).fetchone()

    # Borrar snapshot previo (si existe) y reinsertar
    db.execute('DELETE FROM mensual_persona WHERE id_mensual=?', [m['id_mensual']])

    for fila in filas:
        pid = db.execute('SELECT id_persona FROM persona WHERE dni=?', [fila['dni']]).fetchone()
        if not pid: continue
        n_dias = len(fila['horas_dias'])
        cols  = ','.join([f'd{i}' for i in range(1, n_dias+1)])
        qmarks = ','.join(['?' for _ in range(n_dias)])
        db.execute(f"""INSERT INTO mensual_persona
            (id_mensual,id_persona,nom_c,ap1_c,ap2_c,dni_c,{cols},total_mes)
            VALUES(?,?,?,?,?,?,{qmarks},?)""",
            [m['id_mensual'], pid['id_persona'],
             fila['nom'], fila['ap1'], fila['ap2'], fila['dni']] +
            fila['horas_dias'] + [fila['total']])

    db.execute("UPDATE mensual SET estado='cerrado' WHERE id_mensual=?", [m['id_mensual']])
    db.commit()
    flash(M['mc'], 'success')
    return redirect(url_for('mensual_ver', id_obra=id_obra, id_empresa=id_empresa, mes=mes))

@app.route('/mensual/csv/<int:id_obra>/<int:id_empresa>/<mes>')
def mensual_csv(id_obra, id_empresa, mes):
    obra, empresa, estado, dias, filas = _get_mensual_data(id_obra, id_empresa, mes)
    si = io.StringIO()
    w  = csv.writer(si, delimiter=';')
    cabecera = ['Empresa','Obra','Mes','Nombre','Apellido1','Apellido2','DNI']
    cabecera += [f'Dia_{d}' for d in dias] + ['Total_mes']
    w.writerow(cabecera)
    for f in filas:
        row = [empresa['nombre'], f"{obra['codigo']} {obra['nombre']}", mes,
               f['nom'], f['ap1'], f['ap2'], f['dni']]
        row += [hhmm(h) if h is not None else '' for h in f['horas_dias']]
        row += [hhmm(f['total'])]
        w.writerow(row)
    fname = f"mensual_{mes}_{norm(empresa['nombre'])}_{obra['codigo']}.csv"
    return Response(si.getvalue(), mimetype='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'})

# ═══════════════════════════════════════════════════════════════════════════════
#  RUTAS ── BACKUP
# ═══════════════════════════════════════════════════════════════════════════════
@app.route('/backup')
def backup_page():
    db = get_db()
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bks = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')], reverse=True)
    obras = db.execute("SELECT * FROM obra ORDER BY codigo").fetchall()
    return render_template('backup.html', backups=bks, obras=obras)

@app.route('/backup/crear', methods=['POST'])
def backup_crear():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    id_obra = request.form.get('id_obra','')
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    if id_obra:
        o = get_db().execute('SELECT * FROM obra WHERE id_obra=?', [id_obra]).fetchone()
        suffix = f"_{o['codigo']}_{norm(o['nombre'])}" if o else ''
    else:
        suffix = '_GENERAL'
    fname = f'backup_{ts}{suffix}.db'
    dst_path = os.path.join(BACKUP_DIR, fname)
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dst_path)
    with dst: src.backup(dst)
    src.close(); dst.close()
    flash(M['bk'].format(f=fname), 'success')
    return redirect(url_for('backup_page'))

@app.route('/backup/restaurar', methods=['POST'])
def backup_restaurar():
    fichero = request.form.get('fichero','')
    src_path = os.path.join(BACKUP_DIR, fichero)
    if not os.path.isfile(src_path):
        flash('Fichero de backup no encontrado.', 'error')
        return redirect(url_for('backup_page'))
    close_db()
    shutil.copy2(src_path, DB_PATH)
    flash(M['rs'].format(f=fichero), 'success')
    return redirect(url_for('index'))

# ═══════════════════════════════════════════════════════════════════════════════
#  RUTAS ── CONFIG + FAQ
# ═══════════════════════════════════════════════════════════════════════════════
@app.route('/config', methods=['GET','POST'])
def configuracion():
    db = get_db()
    if request.method == 'POST':
        if request.form.get('reset'):
            lim = 24.0
        else:
            try: lim = float(request.form['limite'])
            except ValueError: lim = 24.0
        lim = max(0.5, min(24.0, lim))
        db.execute('UPDATE config SET limite_horas_dia=? WHERE id_config=1', [lim])
        db.commit(); flash(f'Límite actualizado a {hhmm(lim)} h/día.', 'success')
        return redirect(url_for('configuracion'))
    lim = get_lim()
    return render_template('config.html', act='config', lim=lim)

@app.route('/faq')
def faq():
    return render_template('faq.html', act='faq')

# ═══════════════════════════════════════════════════════════════════════════════
#  ARRANQUE
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, host='127.0.0.1', port=5000)
