'use strict';
/**
 * routes/empresas.js — CRUD de empresas (equivalente a las rutas
 * /empresas/* de app.py).
 */
const express = require('express');
const router = express.Router();
const db = require('../db');
const { renderPage } = require('../middleware/render');
const { ValidationError } = require('../utils');

router.get('/', (req, res) => {
  const conn = db.getDb();
  const emps = conn
    .prepare(
      `SELECT e.*,
        (SELECT count(*) FROM persona WHERE id_empresa=e.id_empresa) n_p,
        (SELECT count(*) FROM obra_empresa WHERE id_empresa=e.id_empresa) n_o
        FROM empresa e ORDER BY e.nombre`
    )
    .all();
  renderPage(req, res, 'empresas/index', { title: 'Empresas', active: 'mas', emps });
});

router.get('/nueva', (req, res) => {
  renderPage(req, res, 'empresas/form', { title: 'Nueva empresa', active: 'mas', emp: null });
});

router.post('/nueva', (req, res) => {
  const conn = db.getDb();
  const nom = (req.body.nombre || '').trim();
  if (!nom) {
    req.flash('Nombre obligatorio.', 'error');
    return res.redirect('/empresas/nueva');
  }
  try {
    conn.prepare('INSERT INTO empresa(nombre) VALUES(?)').run(nom);
    req.flash(`Empresa "${nom}" creada.`, 'success');
    return res.redirect('/empresas/');
  } catch (e) {
    req.flash(`Error: ${e.message}`, 'error');
    return renderPage(req, res, 'empresas/form', { title: 'Nueva empresa', active: 'mas', emp: null });
  }
});

router.get('/:id/editar', (req, res) => {
  const conn = db.getDb();
  const id = parseInt(req.params.id, 10);
  const emp = conn.prepare('SELECT * FROM empresa WHERE id_empresa=?').get(id);
  if (!emp) {
    req.flash('No encontrada.', 'error');
    return res.redirect('/empresas/');
  }
  renderPage(req, res, 'empresas/form', { title: 'Editar empresa', active: 'mas', emp });
});

router.post('/:id/editar', (req, res) => {
  const conn = db.getDb();
  const id = parseInt(req.params.id, 10);
  const emp = conn.prepare('SELECT * FROM empresa WHERE id_empresa=?').get(id);
  if (!emp) {
    req.flash('No encontrada.', 'error');
    return res.redirect('/empresas/');
  }
  const nom = (req.body.nombre || '').trim();
  const est = req.body.estado;
  const metaRaw = (req.body.meta_horas_dia || '').trim();
  let meta = null;
  if (!nom) {
    req.flash('Nombre obligatorio.', 'error');
    return renderPage(req, res, 'empresas/form', { title: 'Editar empresa', active: 'mas', emp });
  }
  try {
    if (metaRaw) {
      meta = parseFloat(metaRaw);
      if (Number.isNaN(meta)) throw new ValidationError('El valor no es un número.');
      if (meta <= 0) throw new ValidationError('La meta debe ser mayor que 0.');
    }
    conn
      .prepare('UPDATE empresa SET nombre=?,estado=?,meta_horas_dia=? WHERE id_empresa=?')
      .run(nom, est, meta, id);
    req.flash(`Empresa "${nom}" actualizada.`, 'success');
    return res.redirect('/empresas/');
  } catch (e) {
    if (e instanceof ValidationError) {
      req.flash(`Meta de horas inválida: ${e.message}`, 'error');
    } else {
      req.flash(`Error: ${e.message}`, 'error');
    }
    return renderPage(req, res, 'empresas/form', { title: 'Editar empresa', active: 'mas', emp });
  }
});

router.post('/:id/eliminar', (req, res) => {
  const conn = db.getDb();
  const id = parseInt(req.params.id, 10);
  try {
    const e = conn.prepare('SELECT nombre FROM empresa WHERE id_empresa=?').get(id);
    conn.prepare('DELETE FROM empresa WHERE id_empresa=?').run(id);
    req.flash(`Empresa "${e ? e.nombre : ''}" eliminada.`, 'success');
  } catch (e) {
    req.flash('No se puede eliminar: hay registros vinculados.', 'error');
  }
  res.redirect('/empresas/');
});

module.exports = router;
