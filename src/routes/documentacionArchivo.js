'use strict';
/**
 * routes/documentacionArchivo.js — descarga de archivos de documentación.
 * Montado en '/documentacion' (distinto del singular '/obra' usado para el
 * resto de rutas de documentación, igual que en la version Python).
 */
const fs = require('fs');
const path = require('path');
const express = require('express');
const router = express.Router();
const db = require('../db');
const config = require('../config');

router.get('/archivo/:id_archivo/descargar', (req, res) => {
  const conn = db.getDb();
  const idArchivo = parseInt(req.params.id_archivo, 10);
  const a = conn.prepare('SELECT * FROM archivo_obra WHERE id_archivo=?').get(idArchivo);
  if (!a) return res.status(404).send('Archivo no encontrado.');
  const rutaAbs = path.join(config.DOCS_DIR, a.ruta_relativa);
  if (!fs.existsSync(rutaAbs) || !fs.statSync(rutaAbs).isFile()) {
    req.flash('El archivo ya no existe en disco.', 'error');
    const c = conn.prepare('SELECT id_obra FROM carpeta_obra WHERE id_carpeta=?').get(a.id_carpeta);
    return res.redirect(c ? `/obra/${c.id_obra}/documentacion` : '/obras/');
  }
  res.download(rutaAbs, a.nombre);
});

module.exports = router;
