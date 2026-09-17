'use strict';
/**
 * routes/cae.js — Gestión de Documentación CAE y PRL (trabajadores y empresas).
 */
const express = require('express');
const router = express.Router();
const db = require('../db');
const { renderPage } = require('../middleware/render');
const {
  TIPOS_DOC_PERSONA,
  TIPOS_DOC_EMPRESA,
  evaluarDocPersona,
  evaluarDocEmpresa,
  hoyIso,
} = require('../services/cae');

// Resumen global de caducidades CAE
router.get('/alertas', (req, res) => {
  const conn = db.getDb();
  const hoy = hoyIso();

  // Documentos de personas caducados o que caducan en los próximos 30 días
  const docsPersonas = conn
    .prepare(
      `SELECT dp.*, p.nombre nom_p, p.apellido1 ap1, p.apellido2 ap2, p.dni, e.nombre nom_e
       FROM documentacion_persona dp
       JOIN persona p ON dp.id_persona=p.id_persona
       LEFT JOIN empresa e ON p.id_empresa=e.id_empresa
       WHERE dp.fecha_caducidad IS NOT NULL AND dp.fecha_caducidad <= date(?, '+30 days')
       ORDER BY dp.fecha_caducidad ASC`
    )
    .all(hoy);

  // Documentos de empresas caducados o que caducan en los próximos 30 días
  const docsEmpresas = conn
    .prepare(
      `SELECT de.*, e.nombre nom_e
       FROM documentacion_empresa de
       JOIN empresa e ON de.id_empresa=e.id_empresa
       WHERE de.fecha_caducidad IS NOT NULL AND de.fecha_caducidad <= date(?, '+30 days')
       ORDER BY de.fecha_caducidad ASC`
    )
    .all(hoy);

  renderPage(req, res, 'cae/alertas', {
    title: 'Alertas CAE y PRL',
    active: 'mas',
    hoy,
    docs_personas: docsPersonas,
    docs_empresas: docsEmpresas,
    tipos_p: TIPOS_DOC_PERSONA,
    tipos_e: TIPOS_DOC_EMPRESA,
  });
});

// Gestión documental de un trabajador
router.get('/persona/:id', (req, res) => {
  const conn = db.getDb();
  const idP = parseInt(req.params.id, 10);
  const p = conn
    .prepare(
      `SELECT p.*, e.nombre nom_e
       FROM persona p LEFT JOIN empresa e ON p.id_empresa=e.id_empresa
       WHERE p.id_persona=?`
    )
    .get(idP);

  if (!p) {
    req.flash('Persona no encontrada.', 'error');
    return res.redirect('/personas/');
  }

  const docs = conn
    .prepare('SELECT * FROM documentacion_persona WHERE id_persona=? ORDER BY fecha_caducidad ASC')
    .all(idP);
  const evaluacion = evaluarDocPersona(conn, idP);

  renderPage(req, res, 'cae/persona', {
    title: `PRL/CAE: ${p.nombre} ${p.apellido1}`,
    active: 'personas',
    p,
    docs,
    evaluacion,
    tipos: TIPOS_DOC_PERSONA,
    hoy: hoyIso(),
  });
});

router.post('/persona/:id/nuevo', (req, res) => {
  const conn = db.getDb();
  const idP = parseInt(req.params.id, 10);
  const tipo = (req.body.tipo_doc || '').trim();
  const desc = (req.body.descripcion || '').trim();
  const fEmision = (req.body.fecha_emision || '').trim() || null;
  const fCad = (req.body.fecha_caducidad || '').trim() || null;
  const obs = (req.body.observaciones || '').trim();

  if (!tipo) {
    req.flash('El tipo de documento es obligatorio.', 'error');
    return res.redirect(`/cae/persona/${idP}`);
  }

  try {
    conn
      .prepare(
        `INSERT INTO documentacion_persona(id_persona, tipo_doc, descripcion, fecha_emision, fecha_caducidad, observaciones)
         VALUES(?,?,?,?,?,?)`
      )
      .run(idP, tipo, desc, fEmision, fCad, obs);
    req.flash('Documento registrado con éxito.', 'success');
  } catch (e) {
    req.flash(`Error al guardar documento: ${e.message}`, 'error');
  }

  res.redirect(`/cae/persona/${idP}`);
});

router.post('/persona/doc/:id_doc/eliminar', (req, res) => {
  const conn = db.getDb();
  const idDoc = parseInt(req.params.id_doc, 10);
  const doc = conn.prepare('SELECT id_persona FROM documentacion_persona WHERE id_doc_persona=?').get(idDoc);
  if (doc) {
    conn.prepare('DELETE FROM documentacion_persona WHERE id_doc_persona=?').run(idDoc);
    req.flash('Documento eliminado.', 'info');
    return res.redirect(`/cae/persona/${doc.id_persona}`);
  }
  res.redirect('/personas/');
});

// Gestión documental de una empresa
router.get('/empresa/:id', (req, res) => {
  const conn = db.getDb();
  const idE = parseInt(req.params.id, 10);
  const e = conn.prepare('SELECT * FROM empresa WHERE id_empresa=?').get(idE);

  if (!e) {
    req.flash('Empresa no encontrada.', 'error');
    return res.redirect('/empresas/');
  }

  const docs = conn
    .prepare('SELECT * FROM documentacion_empresa WHERE id_empresa=? ORDER BY fecha_caducidad ASC')
    .all(idE);
  const evaluacion = evaluarDocEmpresa(conn, idE);

  renderPage(req, res, 'cae/empresa', {
    title: `CAE: ${e.nombre}`,
    active: 'empresas',
    e,
    docs,
    evaluacion,
    tipos: TIPOS_DOC_EMPRESA,
    hoy: hoyIso(),
  });
});

router.post('/empresa/:id/nuevo', (req, res) => {
  const conn = db.getDb();
  const idE = parseInt(req.params.id, 10);
  const tipo = (req.body.tipo_doc || '').trim();
  const desc = (req.body.descripcion || '').trim();
  const fEmision = (req.body.fecha_emision || '').trim() || null;
  const fCad = (req.body.fecha_caducidad || '').trim() || null;
  const obs = (req.body.observaciones || '').trim();

  if (!tipo) {
    req.flash('El tipo de documento es obligatorio.', 'error');
    return res.redirect(`/cae/empresa/${idE}`);
  }

  try {
    conn
      .prepare(
        `INSERT INTO documentacion_empresa(id_empresa, tipo_doc, descripcion, fecha_emision, fecha_caducidad, observaciones)
         VALUES(?,?,?,?,?,?)`
      )
      .run(idE, tipo, desc, fEmision, fCad, obs);
    req.flash('Documento de empresa registrado con éxito.', 'success');
  } catch (e) {
    req.flash(`Error al guardar documento: ${e.message}`, 'error');
  }

  res.redirect(`/cae/empresa/${idE}`);
});

router.post('/empresa/doc/:id_doc/eliminar', (req, res) => {
  const conn = db.getDb();
  const idDoc = parseInt(req.params.id_doc, 10);
  const doc = conn.prepare('SELECT id_empresa FROM documentacion_empresa WHERE id_doc_empresa=?').get(idDoc);
  if (doc) {
    conn.prepare('DELETE FROM documentacion_empresa WHERE id_doc_empresa=?').run(idDoc);
    req.flash('Documento eliminado.', 'info');
    return res.redirect(`/cae/empresa/${doc.id_empresa}`);
  }
  res.redirect('/empresas/');
});

module.exports = router;
