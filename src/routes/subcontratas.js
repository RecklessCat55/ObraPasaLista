'use strict';
/**
 * routes/subcontratas.js — relación empresa principal <-> subcontrata.
 */
const express = require('express');
const router = express.Router();
const db = require('../db');
const { renderPage } = require('../middleware/render');

router.get('/', (req, res) => {
  const conn = db.getDb();
  const rels = conn
    .prepare(
      `SELECT r.*, ep.nombre nom_p, es.nombre nom_s
       FROM empresa_relacion r
       JOIN empresa ep ON r.id_empresa_principal=ep.id_empresa
       JOIN empresa es ON r.id_empresa_subcontrata=es.id_empresa
       ORDER BY ep.nombre, es.nombre`
    )
    .all();
  const emps = conn.prepare("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").all();
  renderPage(req, res, 'subcontratas/index', { title: 'Subcontratas', active: 'mas', rels, emps });
});

router.post('/nueva', (req, res) => {
  const conn = db.getDb();
  const ip = parseInt(req.body.id_principal, 10) || null;
  const iss = parseInt(req.body.id_sub, 10) || null;
  if (!ip || !iss || ip === iss) {
    req.flash('Selecciona empresas distintas.', 'error');
  } else {
    try {
      conn
        .prepare(
          'INSERT OR IGNORE INTO empresa_relacion(id_empresa_principal,id_empresa_subcontrata) VALUES(?,?)'
        )
        .run(ip, iss);
      req.flash('Relación añadida.', 'success');
    } catch (e) {
      req.flash(`Error: ${e.message}`, 'error');
    }
  }
  res.redirect('/subcontratas/');
});

router.post('/:id/eliminar', (req, res) => {
  const conn = db.getDb();
  conn.prepare('DELETE FROM empresa_relacion WHERE id_rel=?').run(parseInt(req.params.id, 10));
  req.flash('Relación eliminada.', 'success');
  res.redirect('/subcontratas/');
});

module.exports = router;
