'use strict';
/**
 * db.js — esquema completo, migraciones y conexión a SQLite.
 *
 * Equivalente a la sección "SCHEMA" + "DB HELPERS" + "MIGRACIÓN" de app.py.
 * Usamos better-sqlite3 (API síncrona) en vez de un pool async: esta app es
 * mono-usuario y local, igual que la versión Flask/sqlite3 original, así que
 * una única conexión compartida por proceso es el equivalente natural de
 * `g.db` (que en Flask vivía una conexión por request, pero apuntaba siempre
 * al mismo fichero).
 */
const Database = require('better-sqlite3');
const config = require('./config');

// -- SCHEMA COMPLETO v1.2 --
const SCHEMA = `
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
`;

const RANGOS_DEFAULT = [
  ['SIN_ESPECIFICAR', 'Sin especificar', 'Rango no asignado'],
  ['PEON', 'Peón', 'Trabajador no cualificado'],
  ['OF2', 'Oficial 2ª', 'Oficial de segunda'],
  ['OF1', 'Oficial 1ª', 'Oficial de primera'],
  ['CAPAZ', 'Capataz', 'Encargado de cuadrilla'],
  ['ENCARG', 'Encargado', 'Encargado de obra'],
];

// -- MIGRACIÓN v1.0 -> v1.1 --
const MIGRATION_V11 = [
  "CREATE TABLE IF NOT EXISTS rango(id_rango INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '')",
  "CREATE TABLE IF NOT EXISTS persona_rango(id_pr INTEGER PRIMARY KEY AUTOINCREMENT, id_persona INTEGER NOT NULL REFERENCES persona(id_persona) ON DELETE CASCADE, id_rango INTEGER NOT NULL REFERENCES rango(id_rango) ON DELETE RESTRICT, fecha_inicio DATE NOT NULL, fecha_fin DATE)",
  "CREATE TABLE IF NOT EXISTS empresa_relacion(id_rel INTEGER PRIMARY KEY AUTOINCREMENT, id_empresa_principal INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT, id_empresa_subcontrata INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT, tipo_relacion TEXT NOT NULL DEFAULT 'subcontrata', fecha_inicio DATE, fecha_fin DATE, UNIQUE(id_empresa_principal, id_empresa_subcontrata))",
  "CREATE TABLE IF NOT EXISTS partida_obra(id_partida INTEGER PRIMARY KEY AUTOINCREMENT, id_obra INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE CASCADE, codigo TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '', UNIQUE(id_obra, codigo))",
  "ALTER TABLE diario ADD COLUMN meteo_estado  TEXT NOT NULL DEFAULT 'soleado'",
  "ALTER TABLE diario ADD COLUMN meteo_detalle TEXT NOT NULL DEFAULT ''",
  'ALTER TABLE diario ADD COLUMN meteo_temp_c  REAL',
  'ALTER TABLE diario_linea ADD COLUMN id_rango   INTEGER REFERENCES rango(id_rango) ON DELETE SET NULL',
  'ALTER TABLE diario_linea ADD COLUMN id_partida INTEGER REFERENCES partida_obra(id_partida) ON DELETE SET NULL',
  'ALTER TABLE mensual_persona ADD COLUMN id_rango       INTEGER REFERENCES rango(id_rango) ON DELETE SET NULL',
  'ALTER TABLE mensual_persona ADD COLUMN id_empresa     INTEGER REFERENCES empresa(id_empresa) ON DELETE SET NULL',
  "ALTER TABLE mensual_persona ADD COLUMN rango_cache    TEXT NOT NULL DEFAULT ''",
  "ALTER TABLE mensual_persona ADD COLUMN empresa_cache  TEXT NOT NULL DEFAULT ''",
  'ALTER TABLE mensual_persona ADD COLUMN es_subcontrata INTEGER NOT NULL DEFAULT 0',
];

// -- MIGRACIÓN v1.1 -> v1.2 --
const MIGRATION_V12 = [
  // 3.1 metas de horas
  'ALTER TABLE persona ADD COLUMN meta_horas_dia REAL',
  'ALTER TABLE empresa ADD COLUMN meta_horas_dia REAL',
  'ALTER TABLE obra    ADD COLUMN meta_horas_dia REAL',
  'ALTER TABLE config  ADD COLUMN umbral_desajuste_meta REAL NOT NULL DEFAULT 2.0 CHECK(umbral_desajuste_meta >= 0)',
  // 3.2 tarifas y costes
  'CREATE TABLE IF NOT EXISTS tarifa_rango(id_rango INTEGER PRIMARY KEY REFERENCES rango(id_rango) ON DELETE CASCADE, precio_hora REAL NOT NULL CHECK(precio_hora >= 0))',
  'ALTER TABLE persona ADD COLUMN precio_hora_override REAL',
  // 3.3 documentación por obra/partida
  "CREATE TABLE IF NOT EXISTS carpeta_obra(id_carpeta INTEGER PRIMARY KEY AUTOINCREMENT, id_obra INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE RESTRICT, id_partida INTEGER REFERENCES partida_obra(id_partida) ON DELETE SET NULL, nombre TEXT NOT NULL, ruta_relativa TEXT NOT NULL, id_padre INTEGER REFERENCES carpeta_obra(id_carpeta) ON DELETE CASCADE, archivada INTEGER NOT NULL DEFAULT 0)",
  'CREATE TABLE IF NOT EXISTS archivo_obra(id_archivo INTEGER PRIMARY KEY AUTOINCREMENT, id_carpeta INTEGER NOT NULL REFERENCES carpeta_obra(id_carpeta) ON DELETE CASCADE, nombre TEXT NOT NULL, ruta_relativa TEXT NOT NULL, tipo_mime TEXT, fecha_subida TEXT NOT NULL, notas TEXT)',
  // 2.3 auditoría
  'CREATE TABLE IF NOT EXISTS log_auditoria(id_log INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, tipo_evento TEXT NOT NULL, entidad TEXT NOT NULL, entidad_id INTEGER NOT NULL, obra_id INTEGER NOT NULL, detalle TEXT NOT NULL)',
  'ALTER TABLE log_auditoria ADD COLUMN obra_id INTEGER', // por si la tabla ya existía sin esta columna
];

let _db = null;

/** Abre (o devuelve) la conexión única a SQLite, con los PRAGMAs de rigor. */
function getDb() {
  if (_db) return _db;
  _db = new Database(config.DB_PATH);
  _db.pragma('foreign_keys = ON');
  _db.pragma('journal_mode = WAL');
  return _db;
}

/** Cierra la conexión activa (si existe) para permitir restaurar el fichero de BD. */
function closeDb() {
  if (_db) {
    _db.close();
    _db = null;
  }
}

function seedRangos(db) {
  const stmt = db.prepare('INSERT OR IGNORE INTO rango(codigo,nombre,descripcion) VALUES(?,?,?)');
  const tx = db.transaction((rows) => {
    for (const [cod, nom, desc] of rows) stmt.run(cod, nom, desc);
  });
  tx(RANGOS_DEFAULT);
}

/** Aplica una lista de statements de migración, ignorando los ya aplicados. */
function aplicarMigracion(db, statements, etiqueta) {
  for (const stmt of statements) {
    try {
      db.exec(stmt);
    } catch (e) {
      const msg = String(e.message || e).toLowerCase();
      if (msg.includes('duplicate column') || msg.includes('already exists')) {
        // ya estaba migrado
      } else {
        console.log(`  ADVERTENCIA (${etiqueta}) ${e.message}`);
      }
    }
  }
}

/** Crea las tablas si no existen y siembra datos base (primer arranque sin CLI). */
function initIfNeeded(db) {
  db.exec(SCHEMA);
  // Si la BD viene de una v1.1 sin pasar por `upgrade-db`, aplicamos también
  // la migración v1.2 aquí (todos los statements son idempotentes).
  aplicarMigracion(db, MIGRATION_V12, 'v1.2 (auto)');
  const cfg = db.prepare('SELECT 1 FROM config WHERE id_config=1').get();
  if (!cfg) {
    db.prepare(
      'INSERT OR IGNORE INTO config(id_config,limite_horas_dia,umbral_desajuste_meta) VALUES(1,24.0,2.0)'
    ).run();
  }
  seedRangos(db);
}

/** flask --app app init-db : instalación limpia, ya en v1.2. */
function cliInitDb(db) {
  db.exec(SCHEMA);
  db.prepare(
    'INSERT OR IGNORE INTO config(id_config,limite_horas_dia,umbral_desajuste_meta) VALUES(1,24.0,2.0)'
  ).run();
  seedRangos(db);
  console.log('OK BD inicializada (v1.2).');
}

/** flask --app app upgrade-db : migra una BD v1.0/v1.1 existente hasta v1.2 (idempotente). */
function cliUpgradeDb(db) {
  aplicarMigracion(db, MIGRATION_V11, 'v1.1');
  aplicarMigracion(db, MIGRATION_V12, 'v1.2');
  db.prepare(
    'INSERT OR IGNORE INTO config(id_config,limite_horas_dia,umbral_desajuste_meta) VALUES(1,24.0,2.0)'
  ).run();
  seedRangos(db);
  // Asignar SIN_ESPECIFICAR a personas sin historial de rango
  const sin = db.prepare("SELECT id_rango FROM rango WHERE codigo='SIN_ESPECIFICAR'").get();
  if (sin) {
    const personas = db.prepare('SELECT id_persona FROM persona').all();
    const chk = db.prepare('SELECT 1 FROM persona_rango WHERE id_persona=?');
    const ins = db.prepare(
      "INSERT INTO persona_rango(id_persona,id_rango,fecha_inicio) VALUES(?,?,'2000-01-01')"
    );
    const tx = db.transaction(() => {
      for (const p of personas) {
        if (!chk.get(p.id_persona)) ins.run(p.id_persona, sin.id_rango);
      }
    });
    tx();
  }
  console.log('OK Migración v1.2 completada.');
}

module.exports = {
  SCHEMA,
  RANGOS_DEFAULT,
  MIGRATION_V11,
  MIGRATION_V12,
  getDb,
  closeDb,
  seedRangos,
  aplicarMigracion,
  initIfNeeded,
  cliInitDb,
  cliUpgradeDb,
};
