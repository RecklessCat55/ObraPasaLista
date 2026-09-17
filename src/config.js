'use strict';
/**
 * config.js — rutas y variables de entorno (equivalente a la cabecera de app.py).
 *
 * Variables de entorno soportadas (igual que en la version Python):
 *   OBRAPL_MODE      'prod' (por defecto) o 'test' -> selecciona app.db / app_test.db
 *   OBRAPL_DOCS_DIR  ruta alternativa para la carpeta de documentación (docs/)
 *   SECRET_KEY       clave de sesión Express (si no se define, se genera una aleatoria)
 *   PORT             puerto HTTP (por defecto 5000, igual que Flask)
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const os = require('os');

const BASE_DIR = path.resolve(__dirname, '..');
const USER_HOME = os.homedir();
const APP_DATA_DIR = path.join(USER_HOME, '.obrapasalista');

const DATA_DIR = path.join(APP_DATA_DIR, 'data');
fs.mkdirSync(DATA_DIR, { recursive: true });

const MODE = process.env.OBRAPL_MODE === 'test' ? 'test' : 'prod';
const DB_NAME = MODE === 'test' ? 'app_test.db' : 'app.db';
const DB_PATH = path.join(DATA_DIR, DB_NAME);
const BACKUP_DIR = path.join(DATA_DIR, 'backups');
fs.mkdirSync(BACKUP_DIR, { recursive: true });

const DOCS_DIR = process.env.OBRAPL_DOCS_DIR || path.join(APP_DATA_DIR, 'docs');
fs.mkdirSync(DOCS_DIR, { recursive: true });

const SECRET_KEY = process.env.SECRET_KEY || crypto.randomBytes(16).toString('hex');

const PORT = parseInt(process.env.PORT || '5000', 10);

/**
 * Compatibilidad con instalaciones v1.1 y el puerto inicial Node.js:
 * Mueve la BD y documentos desde la carpeta del proyecto a la carpeta del usuario.
 */
function migrarUbicacionBdLegacy() {
  if (MODE !== 'prod') return;
  
  // 1. Migración de la BD Python original (BASE_DIR/app.db)
  const legacyPythonDb = path.join(BASE_DIR, 'app.db');
  if (fs.existsSync(legacyPythonDb) && !fs.existsSync(DB_PATH)) {
    try { fs.renameSync(legacyPythonDb, DB_PATH); } catch (e) {}
  }
  const legacyPythonBk = path.join(BASE_DIR, 'backups');
  if (fs.existsSync(legacyPythonBk) && fs.statSync(legacyPythonBk).isDirectory()) {
    try { fs.cpSync(legacyPythonBk, BACKUP_DIR, { recursive: true, force: false }); } catch (e) {}
  }

  // 2. Migración del antiguo puerto Node (BASE_DIR/data y BASE_DIR/docs)
  const legacyNodeDb = path.join(BASE_DIR, 'data', 'app.db');
  if (fs.existsSync(legacyNodeDb) && !fs.existsSync(DB_PATH)) {
    try { fs.renameSync(legacyNodeDb, DB_PATH); } catch (e) {}
  }
  const legacyNodeBk = path.join(BASE_DIR, 'data', 'backups');
  if (fs.existsSync(legacyNodeBk) && fs.statSync(legacyNodeBk).isDirectory()) {
    try { fs.cpSync(legacyNodeBk, BACKUP_DIR, { recursive: true, force: false }); } catch (e) {}
  }
  const legacyNodeDocs = path.join(BASE_DIR, 'docs');
  if (fs.existsSync(legacyNodeDocs) && fs.statSync(legacyNodeDocs).isDirectory()) {
    try { fs.cpSync(legacyNodeDocs, DOCS_DIR, { recursive: true, force: false }); } catch (e) {}
  }
}

module.exports = {
  BASE_DIR,
  DATA_DIR,
  MODE,
  DB_NAME,
  DB_PATH,
  BACKUP_DIR,
  DOCS_DIR,
  SECRET_KEY,
  PORT,
  migrarUbicacionBdLegacy,
};
