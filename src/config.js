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

const BASE_DIR = path.resolve(__dirname, '..');
const DATA_DIR = path.join(BASE_DIR, 'data');
fs.mkdirSync(DATA_DIR, { recursive: true });

const MODE = process.env.OBRAPL_MODE === 'test' ? 'test' : 'prod';
const DB_NAME = MODE === 'test' ? 'app_test.db' : 'app.db';
const DB_PATH = path.join(DATA_DIR, DB_NAME);
const BACKUP_DIR = path.join(DATA_DIR, 'backups');
fs.mkdirSync(BACKUP_DIR, { recursive: true });

const DOCS_DIR = process.env.OBRAPL_DOCS_DIR || path.join(BASE_DIR, 'docs');
fs.mkdirSync(DOCS_DIR, { recursive: true });

const SECRET_KEY = process.env.SECRET_KEY || crypto.randomBytes(16).toString('hex');

const PORT = parseInt(process.env.PORT || '5000', 10);

/**
 * Compatibilidad con instalaciones v1.1: si existe una BD en la ubicación
 * antigua (src/app.db, src/backups/) y todavía no hay nada en data/, se
 * mueven automáticamente. Solo aplica al modo 'prod' con nombre por defecto.
 */
function migrarUbicacionBdLegacy() {
  if (MODE !== 'prod') return;
  const legacyDb = path.join(BASE_DIR, 'app.db');
  if (fs.existsSync(legacyDb) && !fs.existsSync(DB_PATH)) {
    try {
      fs.renameSync(legacyDb, DB_PATH);
    } catch (e) {
      /* ignorado, igual que en la version Python */
    }
  }
  const legacyBk = path.join(BASE_DIR, 'backups');
  if (fs.existsSync(legacyBk) && fs.statSync(legacyBk).isDirectory() && !fs.existsSync(BACKUP_DIR)) {
    try {
      fs.renameSync(legacyBk, BACKUP_DIR);
    } catch (e) {
      /* ignorado */
    }
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
