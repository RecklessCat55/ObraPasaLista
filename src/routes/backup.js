'use strict';
/**
 * routes/backup.js — copias de seguridad de la BD completa (crear/restaurar).
 */
const fs = require('fs');
const path = require('path');
const express = require('express');
const router = express.Router();
const Database = require('better-sqlite3');
const db = require('../db');
const config = require('../config');
const { renderPage } = require('../middleware/render');
const { norm } = require('../services/fechas');
const { crearBackup, verificarIntegridad, backupCompleto } = require('../services/backup');

router.get('/', (req, res) => {
  fs.mkdirSync(config.BACKUP_DIR, { recursive: true });
  const bks = fs
    .readdirSync(config.BACKUP_DIR)
    .filter((f) => f.endsWith('.db'))
    .sort()
    .reverse();
  const obras = db.getDb().prepare('SELECT * FROM obra WHERE deleted_at IS NULL ORDER BY nombre').all();
  renderPage(req, res, 'backup/index', { title: 'Backup', active: 'mas', bks, obras });
});

router.post('/crear', async (req, res) => {
  fs.mkdirSync(config.BACKUP_DIR, { recursive: true });
  const idObra = parseInt(req.body.id_obra, 10) || null;
  let ctx = 'GENERAL';
  if (idObra) {
    const ob = db.getDb().prepare('SELECT codigo,nombre FROM obra WHERE id_obra=?').get(idObra);
    if (ob) ctx = `${ob.codigo}_${norm(ob.nombre)}`;
  }
  try {
    const conn = db.getDb();
    const { ruta, integridadOk } = await backupCompleto(conn, ctx);
    const nombre = path.basename(ruta);
    if (!integridadOk) {
      req.flash(`Backup creado con advertencias de integridad: ${nombre}`, 'warning');
    } else {
      req.flash(`Backup creado: ${nombre}`, 'success');
    }
  } catch (e) {
    req.flash(`Error al crear backup: ${e.message}`, 'error');
  }
  res.redirect('/backup/');
});

router.post('/restaurar', async (req, res) => {
  // 1. Sanitizar y validar nombre de fichero contra traversal
  const rawNombre = String(req.body.nombre || '').trim();
  const nombre = path.basename(rawNombre);
  if (!/^backup_\d{8}_\d{4,6}_[A-Za-z0-9_.-]+\.db$/.test(nombre)) {
    req.flash('Nombre de backup inválido o no permitido.', 'error');
    return res.redirect('/backup/');
  }

  const permitidos = fs
    .readdirSync(config.BACKUP_DIR)
    .filter((f) => /^backup_\d{8}_\d{4,6}_[A-Za-z0-9_.-]+\.db$/.test(f));
  if (!permitidos.includes(nombre)) {
    req.flash('El backup solicitado no existe en la carpeta autorizada.', 'error');
    return res.redirect('/backup/');
  }

  const rutaOrigen = path.join(config.BACKUP_DIR, nombre);
  if (!fs.existsSync(rutaOrigen)) {
    req.flash('Fichero de backup no encontrado.', 'error');
    return res.redirect('/backup/');
  }

  // 2. Comprobar integridad previa y presencia de tablas esenciales antes de tocar nada
  const { ok: integridadOk, detail } = verificarIntegridad(rutaOrigen);
  if (!integridadOk) {
    req.flash(`El backup está corrupto o no es una base de datos válida: ${detail}`, 'error');
    return res.redirect('/backup/');
  }

  let testDb;
  try {
    testDb = new Database(rutaOrigen, { readonly: true });
    const tables = testDb.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map((t) => t.name);
    const requeridas = ['empresa', 'obra', 'persona', 'diario', 'mensual', 'config'];
    const faltantes = requeridas.filter((t) => !tables.includes(t));
    if (faltantes.length > 0) {
      req.flash(`El backup no contiene las tablas mínimas requeridas: ${faltantes.join(', ')}`, 'error');
      return res.redirect('/backup/');
    }
  } catch (e) {
    req.flash(`Error al verificar esquema del backup: ${e.message}`, 'error');
    return res.redirect('/backup/');
  } finally {
    if (testDb) {
      try { testDb.close(); } catch (_) {}
    }
  }

  // 3. Crear copia de seguridad de emergencia de la base activa
  let rutaEmergencia = null;
  try {
    const connActiva = db.getDb();
    rutaEmergencia = await crearBackup(connActiva, 'PRE_RESTORE');
  } catch (e) {
    console.error('No se pudo generar backup de emergencia pre-restauración:', e);
  }

  // 4. Reemplazo atómico con rollback ante fallos
  const tmpPath = config.DB_PATH + '.restore.tmp';
  try {
    fs.copyFileSync(rutaOrigen, tmpPath);

    // Cerrar la conexión activa
    db.closeDb();

    // Eliminar posibles ficheros -wal y -shm residuales de la BD anterior
    try { if (fs.existsSync(config.DB_PATH + '-wal')) fs.unlinkSync(config.DB_PATH + '-wal'); } catch (_) {}
    try { if (fs.existsSync(config.DB_PATH + '-shm')) fs.unlinkSync(config.DB_PATH + '-shm'); } catch (_) {}

    // Sustituir atómicamente el fichero principal
    fs.renameSync(tmpPath, config.DB_PATH);

    // Reabrir y verificar que la base responde y está íntegra
    const nuevaDb = db.getDb();
    const verif = nuevaDb.pragma('integrity_check');
    const okNueva = verif.length === 1 && String(verif[0].integrity_check).toLowerCase() === 'ok';
    if (!okNueva) {
      throw new Error('La base de datos restaurada no superó la verificación de integridad.');
    }
    // Asegurar esquema y posibles migraciones pendientes
    db.initIfNeeded(nuevaDb);

    req.flash(`BD restaurada desde: ${nombre}. Recarga la aplicación.`, 'success');
  } catch (err) {
    console.error('Error durante la restauración, iniciando reversión:', err);
    if (rutaEmergencia && fs.existsSync(rutaEmergencia)) {
      try {
        db.closeDb();
        try { if (fs.existsSync(config.DB_PATH + '-wal')) fs.unlinkSync(config.DB_PATH + '-wal'); } catch (_) {}
        try { if (fs.existsSync(config.DB_PATH + '-shm')) fs.unlinkSync(config.DB_PATH + '-shm'); } catch (_) {}
        fs.copyFileSync(rutaEmergencia, config.DB_PATH);
        db.getDb();
      } catch (revErr) {
        console.error('Fallo en la reversión de emergencia:', revErr);
      }
    }
    try { if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath); } catch (_) {}
    req.flash(`Error al restaurar: ${err.message}. Se preservó la base de datos anterior.`, 'error');
  }

  res.redirect('/backup/');
});

module.exports = router;
