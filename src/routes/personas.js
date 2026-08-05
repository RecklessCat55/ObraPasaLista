'use strict';
/**
 * routes/personas.js — CRUD de personas, historial de rangos, baja lógica,
 * anonimización (RGPD) y borrado seguro.
 */
const express = require('express');
const router = express.Router();
const db = require('../db');
const { renderPage } = require('../middleware/render');
const { fs: fsDate } = require('../services/fechas');
const { usoPersona, chkDesajusteMeta } = require('../services/negocio');

router.get('/', (req, res) => {
  const conn = db.getDb();
  const q = (req.query.q || '').trim();
  const ie = (req.query.id_empresa || '').trim();
  let sql = `SELECT p.*, e.nombre nom_e,
      (SELECT r.nombre FROM persona_rango pr JOIN rango r ON pr.id_rango=r.id_rango
       WHERE pr.id_persona=p.id_persona AND pr.fecha_fin IS NULL
       ORDER BY pr.fecha_inicio DESC LIMIT 1) rango_actual
      FROM persona p LEFT JOIN empresa e ON p.id_empresa=e.id_empresa WHERE 1=1`;
  const params = [];
  if (q) {
    sql += " AND (p.nombre||' '||p.apellido1||' '||p.apellido2||' '||p.dni||' '||p.oficio LIKE ?)";
    params.push(`%${q}%`);
  }
  if (ie) {
    sql += ' AND p.id_empresa=?';
    params.push(ie);
  }
  sql += ' ORDER BY p.apellido1, p.nombre';
  const pers = conn.prepare(sql).all(...params);
  const emps = conn.prepare('SELECT * FROM empresa ORDER BY nombre').all();
  renderPage(req, res, 'personas/index', { title: 'Personas', active: 'mas', pers, emps, q, ie });
});

router.get('/nueva', (req, res) => {
  const conn = db.getDb();
  const emps = conn.prepare("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").all();
  const rangos = conn.prepare("SELECT * FROM rango WHERE codigo!='SIN_ESPECIFICAR' ORDER BY codigo").all();
  renderPage(req, res, 'personas/form', {
    title: 'Nueva persona',
    active: 'mas',
    per: null,
    emps,
    rangos,
    ra: null,
    hist: [],
  });
});

router.post('/nueva', (req, res) => {
  const conn = db.getDb();
  const emps = conn.prepare("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").all();
  const rangos = conn.prepare("SELECT * FROM rango WHERE codigo!='SIN_ESPECIFICAR' ORDER BY codigo").all();
  const f = req.body;
  const nom = (f.nombre || '').trim();
  const ap1 = (f.apellido1 || '').trim();
  const ap2 = (f.apellido2 || '').trim();
  const dni = (f.dni || '').trim();
  const ide = f.id_empresa || null;
  const ofi = (f.oficio || '').trim();
  const idr = f.id_rango || null;
  const errs = [];
  if (!nom) errs.push('Nombre');
  if (!ap1) errs.push('Primer apellido');
  if (!dni) errs.push('DNI');
  if (!idr) errs.push('Rango profesional');
  if (errs.length) {
    req.flash(`Campos obligatorios: ${errs.join(', ')}.`, 'error');
  } else {
    try {
      const metaRaw = (f.meta_horas_dia || '').trim();
      const precioRaw = (f.precio_hora_override || '').trim();
      const meta = metaRaw ? parseFloat(metaRaw) : null;
      const precio = precioRaw ? parseFloat(precioRaw) : null;
      let newId;
      const tx = conn.transaction(() => {
        const cur = conn
          .prepare(
            `INSERT INTO persona(nombre,apellido1,apellido2,dni,id_empresa,oficio,meta_horas_dia,precio_hora_override)
             VALUES(?,?,?,?,?,?,?,?)`
          )
          .run(nom, ap1, ap2, dni, ide, ofi, meta, precio);
        newId = cur.lastInsertRowid;
        conn
          .prepare('INSERT INTO persona_rango(id_persona,id_rango,fecha_inicio) VALUES(?,?,?)')
          .run(newId, idr, fsDate(new Date()));
      });
      tx();
      req.flash(`${ap1}, ${nom} creado.`, 'success');
      if (ide) {
        const w = chkDesajusteMeta(conn, newId, parseInt(ide, 10));
        if (w) req.flash(w, 'warning');
      }
      return res.redirect('/personas/');
    } catch (e) {
      req.flash(`Error: ${e.message}`, 'error');
    }
  }
  renderPage(req, res, 'personas/form', {
    title: 'Nueva persona',
    active: 'mas',
    per: null,
    emps,
    rangos,
    ra: null,
    hist: [],
  });
});

router.get('/:id/editar', (req, res) => {
  const conn = db.getDb();
  const id = parseInt(req.params.id, 10);
  const per = conn.prepare('SELECT * FROM persona WHERE id_persona=?').get(id);
  if (!per) {
    req.flash('No encontrada.', 'error');
    return res.redirect('/personas/');
  }
  const emps = conn.prepare("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").all();
  const rangos = conn.prepare('SELECT * FROM rango ORDER BY codigo').all();
  const ra = conn
    .prepare(
      'SELECT id_rango FROM persona_rango WHERE id_persona=? AND fecha_fin IS NULL ORDER BY fecha_inicio DESC LIMIT 1'
    )
    .get(id);
  const hist = conn
    .prepare(
      `SELECT pr.*,r.nombre nom_r FROM persona_rango pr JOIN rango r ON pr.id_rango=r.id_rango
       WHERE pr.id_persona=? ORDER BY pr.fecha_inicio DESC`
    )
    .all(id);
  renderPage(req, res, 'personas/form', { title: 'Editar persona', active: 'mas', per, emps, rangos, ra, hist });
});

router.post('/:id/editar', (req, res) => {
  const conn = db.getDb();
  const id = parseInt(req.params.id, 10);
  const per = conn.prepare('SELECT * FROM persona WHERE id_persona=?').get(id);
  if (!per) {
    req.flash('No encontrada.', 'error');
    return res.redirect('/personas/');
  }
  const emps = conn.prepare("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").all();
  const rangos = conn.prepare('SELECT * FROM rango ORDER BY codigo').all();
  const ra = conn
    .prepare(
      'SELECT id_rango FROM persona_rango WHERE id_persona=? AND fecha_fin IS NULL ORDER BY fecha_inicio DESC LIMIT 1'
    )
    .get(id);
  const hist = conn
    .prepare(
      `SELECT pr.*,r.nombre nom_r FROM persona_rango pr JOIN rango r ON pr.id_rango=r.id_rango
       WHERE pr.id_persona=? ORDER BY pr.fecha_inicio DESC`
    )
    .all(id);

  const f = req.body;
  const nom = (f.nombre || '').trim();
  const ap1 = (f.apellido1 || '').trim();
  const ap2 = (f.apellido2 || '').trim();
  const dni = (f.dni || '').trim();
  const ide = f.id_empresa || null;
  const ofi = (f.oficio || '').trim();
  const est = f.estado;
  const newR = f.id_rango_nuevo || null;

  if (!nom || !ap1 || !dni) {
    req.flash('Nombre, primer apellido y DNI obligatorios.', 'error');
  } else {
    try {
      const metaRaw = (f.meta_horas_dia || '').trim();
      const precioRaw = (f.precio_hora_override || '').trim();
      const meta = metaRaw ? parseFloat(metaRaw) : null;
      const precio = precioRaw ? parseFloat(precioRaw) : null;
      const tx = conn.transaction(() => {
        conn
          .prepare(
            `UPDATE persona SET nombre=?,apellido1=?,apellido2=?,dni=?,id_empresa=?,oficio=?,estado=?,
             meta_horas_dia=?,precio_hora_override=? WHERE id_persona=?`
          )
          .run(nom, ap1, ap2, dni, ide, ofi, est, meta, precio, id);
        if (newR) {
          const hoyS = fsDate(new Date());
          conn
            .prepare('UPDATE persona_rango SET fecha_fin=? WHERE id_persona=? AND fecha_fin IS NULL')
            .run(hoyS, id);
          conn
            .prepare('INSERT INTO persona_rango(id_persona,id_rango,fecha_inicio) VALUES(?,?,?)')
            .run(id, newR, hoyS);
        }
      });
      tx();
      req.flash(`${ap1}, ${nom} actualizado.`, 'success');
      if (ide) {
        const w = chkDesajusteMeta(conn, id, parseInt(ide, 10));
        if (w) req.flash(w, 'warning');
      }
      return res.redirect('/personas/');
    } catch (e) {
      req.flash(`Error: ${e.message}`, 'error');
    }
  }
  renderPage(req, res, 'personas/form', { title: 'Editar persona', active: 'mas', per, emps, rangos, ra, hist });
});

/**
 * Hard delete seguro: solo si NO tiene uso en diarios ni mensuales.
 * Si tiene histórico, se bloquea y se sugiere baja/anonimizar.
 */
router.post('/:id/eliminar', (req, res) => {
  const conn = db.getDb();
  const id = parseInt(req.params.id, 10);
  const p = conn.prepare('SELECT nombre, apellido1 FROM persona WHERE id_persona=?').get(id);
  if (!p) {
    req.flash('Persona no encontrada.', 'error');
    return res.redirect('/personas/');
  }
  const uso = usoPersona(conn, id);
  if (uso.diario || uso.mensual) {
    req.flash(
      `No se puede eliminar: tiene ${uso.diario} parte(s) diaria(s) y ` +
        `${uso.mensual} registro(s) mensual(es). Ponla como inactiva o anonimízala.`,
      'error'
    );
    return res.redirect('/personas/');
  }
  conn.prepare('DELETE FROM persona WHERE id_persona=?').run(id);
  req.flash(`${p.apellido1}, ${p.nombre} eliminada definitivamente.`, 'success');
  res.redirect('/personas/');
});

/** Baja lógica: estado='inactiva'. No rompe histórico ni FKs. */
router.post('/:id/baja', (req, res) => {
  const conn = db.getDb();
  const id = parseInt(req.params.id, 10);
  const p = conn.prepare('SELECT nombre, apellido1, estado FROM persona WHERE id_persona=?').get(id);
  if (!p) {
    req.flash('Persona no encontrada.', 'error');
    return res.redirect('/personas/');
  }
  if (p.estado === 'inactiva') {
    req.flash('La persona ya está inactiva.', 'info');
    return res.redirect('/personas/');
  }
  conn.prepare("UPDATE persona SET estado='inactiva' WHERE id_persona=?").run(id);
  req.flash(`${p.apellido1}, ${p.nombre} marcada como inactiva.`, 'success');
  res.redirect('/personas/');
});

/**
 * Anonimiza una persona manteniendo histórico (RGPD-friendly).
 * Marca la persona como inactiva y borra datos identificables.
 */
router.post('/:id/anonimizar', (req, res) => {
  const conn = db.getDb();
  const id = parseInt(req.params.id, 10);
  const p = conn.prepare('SELECT nombre, apellido1, apellido2, dni FROM persona WHERE id_persona=?').get(id);
  if (!p) {
    req.flash('Persona no encontrada.', 'error');
    return res.redirect('/personas/');
  }
  const uso = usoPersona(conn, id);
  if (!(uso.diario || uso.mensual)) {
    req.flash('Esta persona no tiene histórico; elimínala en lugar de anonimizarla.', 'warning');
    return res.redirect('/personas/');
  }
  const anonTag = `ANON_${id}`;
  conn
    .prepare(
      `UPDATE persona
         SET nombre    = ?,
             apellido1 = ?,
             apellido2 = '',
             dni       = ?,
             oficio    = '',
             estado    = 'inactiva'
       WHERE id_persona=?`
    )
    .run(anonTag, 'ANONIMIZADO', anonTag, id);
  req.flash(
    `Persona #${id} anonimizada. Se mantiene el histórico de horas, ` +
      'pero ya no es identificable y no se puede usar en nuevos partes.',
    'success'
  );
  res.redirect('/personas/');
});

module.exports = router;
