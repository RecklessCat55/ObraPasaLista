'use strict';
/**
 * routes/backup.js — copias de seguridad de la BD completa (crear/restaurar).
 */
const fs = require('fs');
const path = require('path');
const express = require('express');
const router = express.Router();
const db = require('../db');
const config = require('../config');
const { renderPage } = require('../middleware/render');
const { norm } = require('../services/fechas');

router.get('/', (req, res) => {
  fs.mkdirSync(config.BACKUP_DIR, { recursive: true });
  const bks = fs
    .readdirSync(config.BACKUP_DIR)
    .filter((f) => f.endsWith('.db'))
    .sort()
    .reverse();
  const obras = db.getDb().prepare('SELECT * FROM obra ORDER BY nombre').all();
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
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}`;
  const nombre = `backup_${stamp}_${ctx}.db`;
  const ruta = path.join(config.BACKUP_DIR, nombre);
  try {
    await db.getDb().backup(ruta);
    req.flash(`Backup creado: ${nombre}`, 'success');
  } catch (e) {
    req.flash(`Error: ${e.message}`, 'error');
  }
  res.redirect('/backup/');
});

router.post('/restaurar', (req, res) => {
  const nombre = (req.body.nombre || '').trim();
  const ruta = path.join(config.BACKUP_DIR, nombre);
  if (!fs.existsSync(ruta)) {
    req.flash('Backup no encontrado.', 'error');
    return res.redirect('/backup/');
  }
  try {
    db.closeDb();
    fs.copyFileSync(ruta, config.DB_PATH);
    db.getDb(); // reabre la conexión sobre el fichero restaurado
    req.flash(`BD restaurada desde: ${nombre}. Recarga la aplicación.`, 'success');
  } catch (e) {
    req.flash(`Error: ${e.message}`, 'error');
  }
  res.redirect('/backup/');
});

module.exports = router;
