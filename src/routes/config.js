'use strict';
/**
 * routes/config.js — configuración general (límite h/día) y metas de horas
 * por persona/empresa/obra (4.4).
 */
const express = require('express');
const router = express.Router();
const db = require('../db');
const { renderPage } = require('../middleware/render');
const { hhmm } = require('../services/fechas');
const { getLim } = require('../services/horas');
const { getUmbralDesajuste, listarDesajustesMeta } = require('../services/negocio');

router.get('/', (req, res) => {
  const conn = db.getDb();
  const lim = getLim(conn);
  renderPage(req, res, 'config/index', { title: 'Config', active: 'mas', lim, hhmm });
});

router.post('/', (req, res) => {
  const conn = db.getDb();
  const accion = req.body.accion;
  if (accion === 'reset') {
    conn.prepare('UPDATE config SET limite_horas_dia=24.0 WHERE id_config=1').run();
    req.flash('Límite restablecido a 24 h/día.', 'success');
  } else if (accion === 'guardar') {
    try {
      const lim = parseFloat(req.body.limite);
      if (Number.isNaN(lim) || lim <= 0) throw new Error('inválido');
      conn.prepare('UPDATE config SET limite_horas_dia=? WHERE id_config=1').run(lim);
      req.flash(`Límite actualizado a ${hhmm(lim)}.`, 'success');
    } catch (e) {
      req.flash('Valor inválido.', 'error');
    }
  }
  res.redirect('/config/');
});

router.get('/metas', (req, res) => {
  const conn = db.getDb();
  const empresas = conn.prepare("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").all();
  const obras = conn.prepare("SELECT * FROM obra ORDER BY (estado='finalizada'), nombre").all();
  const personas = conn
    .prepare(
      `SELECT p.*, e.nombre nom_e FROM persona p LEFT JOIN empresa e ON p.id_empresa=e.id_empresa
       WHERE p.estado='activa' ORDER BY p.apellido1, p.nombre`
    )
    .all();
  const umbral = getUmbralDesajuste(conn);
  const avisos = listarDesajustesMeta(conn);
  renderPage(req, res, 'config/metas', {
    title: 'Metas de horas',
    active: 'mas',
    empresas,
    obras,
    personas,
    umbral,
    avisos,
    hhmm,
  });
});

router.post('/metas', (req, res) => {
  const conn = db.getDb();
  try {
    const umbral = parseFloat(req.body.umbral_desajuste_meta);
    if (Number.isNaN(umbral) || umbral < 0) throw new Error('inválido');
    conn.prepare('UPDATE config SET umbral_desajuste_meta=? WHERE id_config=1').run(umbral);
    req.flash(`Umbral de desajuste actualizado a ${hhmm(umbral)}.`, 'success');
  } catch (e) {
    req.flash('Umbral inválido.', 'error');
  }
  res.redirect('/config/metas');
});

function guardarMeta(conn, req, tabla, pk, id) {
  const raw = (req.body.meta_horas_dia || '').trim();
  try {
    const meta = raw ? parseFloat(raw) : null;
    if (meta !== null && (Number.isNaN(meta) || meta <= 0)) throw new Error('inválido');
    conn.prepare(`UPDATE ${tabla} SET meta_horas_dia=? WHERE ${pk}=?`).run(meta, id);
    req.flash('Meta actualizada.', 'success');
  } catch (e) {
    req.flash('Meta de horas inválida.', 'error');
  }
}

router.post('/metas/persona/:id', (req, res) => {
  guardarMeta(db.getDb(), req, 'persona', 'id_persona', parseInt(req.params.id, 10));
  res.redirect('/config/metas');
});

router.post('/metas/empresa/:id', (req, res) => {
  guardarMeta(db.getDb(), req, 'empresa', 'id_empresa', parseInt(req.params.id, 10));
  res.redirect('/config/metas');
});

router.post('/metas/obra/:id', (req, res) => {
  const conn = db.getDb();
  const id = parseInt(req.params.id, 10);
  const ob = conn.prepare('SELECT estado FROM obra WHERE id_obra=?').get(id);
  if (ob && ob.estado === 'finalizada') {
    req.flash('La obra está finalizada: la meta de horas no es editable.', 'error');
    return res.redirect('/config/metas');
  }
  guardarMeta(conn, req, 'obra', 'id_obra', id);
  res.redirect('/config/metas');
});

module.exports = router;
