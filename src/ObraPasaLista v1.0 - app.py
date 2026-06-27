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
    <td>{{ p.apellido1 }}{% if p.apell